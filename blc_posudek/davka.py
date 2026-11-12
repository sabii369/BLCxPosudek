"""
davka.py
========
Výpočet jednoho vstupu (posouzení / zatížitelnost) bez GUI a dávka více souborů se
souhrnem souhrn.csv (spouští python -m blc_posudek; funkce jsou v samostatném modulu, aby je
mohly volat procesy -j N – na Windows se __main__.py balíčku v podprocesu nenačte).
"""

from __future__ import annotations
import csv
import glob
import os
import time


def _vstupy(cesty: list) -> list:
    """Seznam vstupních souborů; složka = všechny *.toml a *.json v ní (abecedně)."""
    out = []
    for c in cesty:
        if os.path.isdir(c):
            out += sorted(glob.glob(os.path.join(c, "*.toml")) + glob.glob(os.path.join(c, "*.json")))
        else:
            out.append(c)
    return out


def vypocet_souboru(cesta: str, vystup: str | None, zatizitelnost: bool = False, druhy=None,
                    protokol=None, bez_protokolu: bool = False, prubeh=None) -> dict:
    """Výpočet jednoho vstupu (posouzení nebo zatížitelnost) a uložení výstupů do složky
    vystup (není-li bez_protokolu).  Vrací {d, vys, o, model, res, zat, out, dalsi, most}."""
    import matplotlib
    matplotlib.use("Agg")
    from blc.export_pb import uloz_vysledky
    from blc.vstup_sily import uloz_grafy
    from .vypocet import nacti, spocti, uloz_protokol_most as uloz_protokol
    d = nacti(cesta)
    zat = zatizitelnost or bool(d.get("blc", {}).get("zatizitelnost"))
    dalsi, res = [], None                         # (složka, model) – protokoly druhů
    if zat:
        from .zatizitelnost import zatizitelnost as zat_fn, protokol_ze_vstupu, protokol_druhu
        prot = protokol_ze_vstupu(d, protokol)
        res = zat_fn(d, druhy=druhy, prubeh=prubeh, protokol=prot)
        model = protokol_druhu(res, "souhrn" if prot == "vse" else prot, prubeh)
        vys, o = model.blc["vys"], model.blc["o"]
        if prot == "vse" and not bez_protokolu:
            dalsi = [(os.path.join(vystup, dr), protokol_druhu(res, dr, prubeh)) for dr in res.druhy]
    else:
        vys, o, model = spocti(d)
    out = most = None
    if not bez_protokolu:
        out = uloz_protokol(model, vystup)
        for adr, m in dalsi:
            uloz_protokol(m, adr)
        most = os.path.join(vystup, "most")
        uloz_vysledky(vys, most, vystup=vys.popisky[o])
        uloz_grafy(vys, most, vys.popisky[o])
    return dict(d=d, vys=vys, o=o, model=model, res=res, zat=zat, out=out, dalsi=dalsi, most=most)


# ---------------------------------------------------------------------------
# Souhrn dávky (více souborů)
# ---------------------------------------------------------------------------

SLOUPCE = ["soubor", "most", "nosnik", "vozidlo", "posudku", "nevyhovuje", "eta_MSU [%]",
           "rozhoduje_MSU", "eta_MSP [%]", "rozhoduje_MSP", "upozorneni", "vysledek",
           "Vn [t]", "Vr [t]", "Ve [t]", "Vn_evidence [t]", "Vr_evidence [t]", "Ve_evidence [t]",
           "Vaj [t]", "rozhoduje_zatizitelnost", "protokol", "cas [s]", "chyba"]


def _maximum(posudky, ms):
    p = [v for v in posudky if v.mezni_stav == ms]
    return max(p, key=lambda v: v.vyuziti) if p else None


def radek_souhrnu(cesta: str, r: dict) -> dict:
    """Řádek souhrnu dávky z výsledku vypocet_souboru (čísla jako float, prázdné = None)."""
    vys, o, model, res = r["vys"], r["o"], r["model"], r["res"]
    pos = model.protokol.posudky
    nok = [v for v in pos if not v.vyhovuje]
    row = {k: None for k in SLOUPCE}
    row.update(soubor=os.path.basename(cesta), most=vys.popis, nosnik=vys.popisky[o],
               vozidlo=vys.vozidlo, posudku=len(pos), nevyhovuje=len(nok),
               upozorneni=len(model.protokol.upozorneni), protokol=r["out"] and str(r["out"]))
    for ms, k in (("MSÚ", "MSU"), ("MSP", "MSP")):
        mx = _maximum(pos, ms)
        if mx is not None:
            row[f"eta_{k} [%]"] = mx.vyuziti * 100
            row[f"rozhoduje_{k}"] = f"{mx.nazev} – {mx.faze}"
    if res is None:
        row["vysledek"] = "VYHOVUJE" if not nok else "NEVYHOVUJE"
    else:
        row["vysledek"] = "zatížitelnost"
        for dr, z in res.druhy.items():
            row[f"{dr} [t]"] = z.V
            row[f"{dr}_evidence [t]"] = z.V_evidence
        row["Vaj [t]"] = res.Vaj
        m = res.minimum()
        if m is not None:
            row["rozhoduje_zatizitelnost"] = f"{res.druh}: {m.klic[0]} {m.klic[1]} ({m.klic[2]})"
    return row


def jedno_vlakno() -> None:
    """numpy / OpenBLAS v jednom vlákně (nemá-li uživatel nastaveno jinak).  Úlohy MKP jsou
    malé – vícevláknové BLAS je zpomaluje (most KA67/12: 1,34 s → 0,89 s) a souběžné procesy
    dávky -j N by si přetahovaly všechna jádra.  Účinné jen před prvním importem numpy."""
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(k, "1")


def _zpracuj(uloha: tuple) -> dict:
    """Jeden soubor dávky (spouští se i v samostatném procesu) → řádek souhrnu."""
    cesta, vystup, volby = uloha
    t0 = time.perf_counter()
    try:
        row = radek_souhrnu(cesta, vypocet_souboru(cesta, vystup, **volby))
    except Exception as e:  # noqa: BLE001 – chyba jednoho souboru nezastaví dávku
        row = {k: None for k in SLOUPCE}
        row.update(soubor=os.path.basename(cesta), vysledek="CHYBA", chyba=f"{type(e).__name__}: {e}")
    row["cas [s]"] = time.perf_counter() - t0
    return row


def uloz_souhrn(radky: list, cesta: str) -> None:
    """souhrn.csv: oddělovač ;, desetinná čárka, UTF-8 s BOM (Excel)."""
    from blc.cisla import cz
    os.makedirs(os.path.dirname(os.path.abspath(cesta)), exist_ok=True)
    with open(cesta, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(SLOUPCE)
        for r in radky:
            w.writerow(["" if r.get(k) is None else cz(r[k], 2) if isinstance(r[k], float) else r[k]
                        for k in SLOUPCE])


def davka(soubory: list, vystup: str | None, volby: dict, jobs: int = 1) -> int:
    """Výpočet více souborů → DIR/<soubor>/ a DIR/souhrn.csv.  Návratový kód: 2 = chyba
    některého souboru, 1 = některý posudek nevyhovuje, jinak 0."""
    from blc.cisla import cz
    vystup = vystup or os.path.join(os.path.dirname(os.path.abspath(soubory[0])), "vystup_davka")
    ulohy = [(c, os.path.join(vystup, os.path.splitext(os.path.basename(c))[0]), volby)
             for c in soubory]
    n = len(ulohy)
    radky = [None] * n

    def hlas(i, r):
        if r["chyba"]:
            txt = f"CHYBA – {r['chyba']}"
        elif r["vysledek"] == "zatížitelnost":
            txt = ", ".join(f"{dr} {cz(r[f'{dr} [t]'], 1)} t" for dr in ("Vn", "Vr", "Ve")
                            if r.get(f"{dr} [t]") is not None) or "zatížitelnost neomezena"
        else:
            txt = (f"{r['vysledek']}, η MSÚ {cz(r['eta_MSU [%]'] or 0.0, 1)} %, "
                   f"MSP {cz(r['eta_MSP [%]'] or 0.0, 1)} %")
        print(f"[{i + 1}/{n}] {r['soubor']}: {txt} ({cz(r['cas [s]'], 1)} s)", flush=True)

    t0 = time.perf_counter()
    if jobs > 1 and n > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=min(jobs, n), initializer=jedno_vlakno) as ex:
            fut = {ex.submit(_zpracuj, u): i for i, u in enumerate(ulohy)}
            for k, f in enumerate(as_completed(fut)):
                radky[fut[f]] = r = f.result()
                hlas(k, r)
    else:
        for i, u in enumerate(ulohy):
            radky[i] = _zpracuj(u)
            hlas(i, radky[i])
    souhrn = os.path.join(vystup, "souhrn.csv")
    uloz_souhrn(radky, souhrn)
    chyb = sum(1 for r in radky if r["chyba"])
    nok = sum(1 for r in radky if r["vysledek"] == "NEVYHOVUJE")
    print(f"\nSouborů {n} za {cz(time.perf_counter() - t0, 1)} s; nevyhovuje {nok}, chyb {chyb}."
          f"\nSouhrn: {souhrn}")
    return 2 if chyb else 1 if nok else 0
