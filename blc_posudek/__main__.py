"""
Spuštění spojeného programu BLC × Posudek PB.

  python -m blc_posudek                       GUI (otevře příklad priklady/most_KA67_12.toml)
  python -m blc_posudek soubor.toml --gui     GUI se souborem
  python -m blc_posudek soubor.toml [-o DIR]  dávkově: most (BLC) → posudek → HTML protokol
                                              + vnitřní síly mostu do DIR/most
  python -m blc_posudek soubor.toml --zatizitelnost [--druhy Vn,Vr,Ve]
                                              zatížitelnost podle ČSN 73 6222: Vn, Vr, Ve pro
                                              η = 100 % každého mezního stavu (též [blc]
                                              zatizitelnost = true, zatizitelnost_druhy)
      [--protokol souhrn|Vn|Vr|Ve|vse]        protokol: souhrn (všechny druhy, posudky pro
                                              zvolené vozidlo), jen jeden druh (posudky při
                                              jeho zatížitelnosti), vse = souhrn + DIR/<druh>/
  python -m blc_posudek a.toml b.toml … | SLOŽKA [-o DIR] [-j N] [--bez-protokolu]
                                              více souborů (složka = všechny *.toml, *.json):
                                              výstup každého do DIR/<soubor>/, souhrn všech
                                              do DIR/souhrn.csv (výchozí DIR = vystup_davka
                                              vedle prvního vstupu); -j = počet procesů
  --bez-protokolu                             jen výpočet a výpis / souhrn (bez HTML, grafů
                                              a vnitřních sil mostu – výrazně rychlejší)
"""

from __future__ import annotations
import argparse
import os
import sys

from .davka import _vstupy, davka, jedno_vlakno, vypocet_souboru


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    jedno_vlakno()                       # před importem numpy (výpočet, GUI i procesy dávky)
    ap = argparse.ArgumentParser(prog="python -m blc_posudek",
                                 description="BLC × Posudek PB – most → zatížení nosníku → posudek")
    ap.add_argument("vstup", nargs="*", help="vstupní soubor(y) .toml / .json nebo složka "
                                             "(bez vstupu se otevře GUI)")
    ap.add_argument("--gui", action="store_true", help="otevřít soubor v grafickém rozhraní")
    ap.add_argument("-o", "--vystup", default=None, help="výstupní složka (výchozí vystup_<soubor>, "
                                                          "u více souborů vystup_davka)")
    ap.add_argument("--zatizitelnost", action="store_true",
                    help="místo posouzení hledat Vn, Vr, Ve pro využití 100 %% v každém mezním stavu")
    ap.add_argument("--druhy", default=None,
                    help="druhy zatížitelnosti, např. Vn,Vr,Ve (výchozí [blc] zatizitelnost_druhy "
                         "= vše); protokol je pro zvolené vozidlo")
    ap.add_argument("--protokol", default=None, choices=("souhrn", "Vn", "Vr", "Ve", "vse"),
                    help="protokol zatížitelnosti: souhrn (výchozí, [blc] protokol_zatizitelnosti), "
                         "jen Vn / Vr / Ve (posudky při jeho zatížitelnosti), vse = souhrn + "
                         "protokol každého druhu do podsložky")
    ap.add_argument("--bez-protokolu", action="store_true",
                    help="jen výpočet a výpis / souhrn – bez HTML protokolu, grafů a vnitřních sil "
                         "mostu (rychlejší, např. pro parametrickou studii)")
    ap.add_argument("-j", "--jobs", type=int, default=1,
                    help="počet souběžných procesů při více souborech (výchozí 1)")
    a = ap.parse_args(argv)
    if a.gui or not a.vstup:
        if len(a.vstup) > 1:
            ap.error("GUI otevře jen jeden soubor.")
        from .gui import main as gui_main
        return gui_main(a.vstup[:1])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    volby = dict(zatizitelnost=a.zatizitelnost, druhy=a.druhy, protokol=a.protokol,
                 bez_protokolu=a.bez_protokolu)
    soubory = _vstupy(a.vstup)
    if not soubory:
        print(f"[CHYBA] {', '.join(a.vstup)}: žádný vstupní soubor (*.toml, *.json).", file=sys.stderr)
        return 2
    if len(soubory) > 1 or os.path.isdir(a.vstup[0]):
        return davka(soubory, a.vystup, volby, max(1, a.jobs))
    return jeden_soubor(soubory[0], a.vystup, volby)


def jeden_soubor(cesta: str, vystup: str | None, volby: dict) -> int:
    from pb_posudek.protokol import fmt
    from blc.cisla import cz
    vystup = vystup or os.path.join(os.path.dirname(os.path.abspath(cesta)),
                                    "vystup_" + os.path.splitext(os.path.basename(cesta))[0])
    pr = lambda t: print(t, flush=True)  # noqa: E731
    try:
        r = vypocet_souboru(cesta, vystup, prubeh=pr, **volby)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[CHYBA] {cesta}: {e}", file=sys.stderr)
        return 2
    vys, o, model, res, out, most = r["vys"], r["o"], r["model"], r["res"], r["out"], r["most"]
    ulozeno = (f"Protokol: {out}\nVnitřní síly mostu: {most}" if out else
               "Protokol a vnitřní síly mostu se neukládají (--bez-protokolu).")
    print(f"Most: {vys.popis}\nVozidlo: {vys.vozidlo}; posuzovaný nosník {vys.popisky[o]}\n")
    if r["zat"]:
        from .zatizitelnost import NAZVY_DRUHU
        druhy = list(res.druhy)
        zp = {dr: {p.klic: p for p in z.posudky} for dr, z in res.druhy.items()}
        print(f"{'MS':4} {'Posudek':42} {'Fáze':28} " + " ".join(f"{dr + ' [t]':>9}" for dr in druhy))
        for p in sorted(res.posudky, key=lambda p: (p.V is None, p.V or 0.0)):
            print(f"{p.klic[0]:4} {p.klic[1][:42]:42} {p.klic[2][:28]:28} " +
                  " ".join(f"{zp[dr][p.klic].kratky if p.klic in zp[dr] else '–':>9}" for dr in druhy))
        print("\nZatížitelnost (ČSN 73 6222; ∞ = neomezuje / nezávisí, ✗ = nevyhovuje nezávisle):")
        for dr, z in res.druhy.items():
            m = z.minimum()
            print(f"  {dr} ({NAZVY_DRUHU[dr]}): " +
                  (f"{cz(m.V, 1)} t → evidence {z.V_evidence} t – {m.klic[0]} {m.klic[1]} ({m.klic[2]}), "
                   f"nosník {z.prvni.vys.popisky[z.o]}" if m else f"> {z.V_max:.0f} t"))
        if res.Vaj is not None:
            print(f"  V_aj (jedna náprava, čl. 5.1.7): {cz(res.Vaj, 1)} t")
        for t in res.poznamky:
            print("! " + t)
        mz = model.zatizitelnost
        for t in model.protokol.upozorneni:
            print(f"! Upozornění ({mz.druh} = {cz(vys.V, 1)} t): {t}")
        print(f"Posudky ({'jen ' + mz.druh if mz.jen_druh else 'souhrn'}) pro {mz.druh} = "
              f"{cz(vys.V, 1)} t.\n{ulozeno}")
        for adr, m in r["dalsi"]:
            print(f"Protokol jen {m.zatizitelnost.druh} (posudky pro {m.zatizitelnost.druh} = "
                  f"{cz(m.blc['vys'].V, 1)} t): {os.path.join(adr, 'protokol.html')}")
        return 0
    print(f"{'MS':4} {'Posudek':42} {'Fáze':28} {'x [m]':>7} {'η':>8}")
    for v in model.protokol.posudky:
        print(f"{v.mezni_stav:4} {v.nazev[:42]:42} {v.faze[:28]:28} "
              f"{fmt(v.x, 3) if v.x is not None else '–':>7} {cz(v.vyuziti * 100, 1) + ' %':>8} "
              f"{'OK' if v.vyhovuje else 'NEVYHOVUJE'}")
    for t in model.protokol.upozorneni:
        print(f"! Upozornění: {t}")
    ok = all(v.vyhovuje for v in model.protokol.posudky)
    print(f"\n{ulozeno}\nCelkem: {'VYHOVUJE' if ok else 'NEVYHOVUJE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
