"""
export_pb.py
============
Uložení vnitřních sil (vnitrni_sily.VysledekSil) a export do modulu Posudek PB
(repo PB_posudek, vstup TOML, sekce [zatizeni]).

Soubory ve výstupní složce:
  vnitrni_sily.json        vše: metadata, souhrn, průběhy g0, g−g0, q na všech výstupech
  souhrn.csv               max M, |V| po výstupech (Excel: oddělovač ;, desetinná čárka)
  <výstup>_stavy.csv       průběhy stavů posuzovaného výstupu
  zatizeni_PB.toml         sekce [zatizeni] pro Posudek PB (posuzovaný výstup)
  <vstup PB>_BLC.toml      (volitelně) vstup posudku se sekcí [zatizeni] nahrazenou

Posudek PB řeší prostý nosník délky L s ložisky ve vzdálenosti (L − L0)/2 od
konců; x posudku = x od osy první podpory + (L − L0)/2.  Vlastní tíhu nosníku g0
počítá posudek sám z průřezu, proto se do zatížení výchozí převádí jen g − g0
a q (obsahuje_vlastni_tihu = false); g0 z BLC je v komentáři pro kontrolu.

Režimy zatížení posudku:
  "kombinace"         (výchozí) obálky kombinací 6.10a, 6.10b (nebo 6.10), char,
                      častá, kvazistálá – přesně max/min M i V,
  "zatezovaci_stavy"  stálé g − g0 (tabulka x, M, V) + proměnné q (tabulka x, M_max,
                      V s větší absolutní hodnotou z V_max / V_min) – kombinace
                      sestaví posudek sám.
"""

from __future__ import annotations
import csv
import json
import os
import re
import tomllib
from typing import List, Optional

import numpy as np

from . import __version__
from .vnitrni_sily import VysledekSil, TabulkaSil, NAZVY_STAVU

NAZVY_KOMBINACI_PB = {
    "6.10a": "MSÚ (6.10a)", "6.10b": "MSÚ (6.10b)", "6.10": "MSÚ (6.10)",
    "char": "charakteristická", "casta": "častá", "kvazistala": "kvazistálá",
}


# ---------------------------------------------------------------------------
# Pomocné – TOML zápis
# ---------------------------------------------------------------------------

def _cislo(v: float, des: int) -> str:
    t = f"{float(v):.{des}f}"
    return "0.0" if t in (f"-{0:.{des}f}", f"{0:.{des}f}") else t


def _pole(hodnoty, des: int = 2, na_radek: int = 8, odsazeni: str = "    ") -> str:
    h = [_cislo(v, des) for v in hodnoty]
    if len(h) <= na_radek:
        return "[" + ", ".join(h) + "]"
    radky = [odsazeni + ", ".join(h[i:i + na_radek]) + "," for i in range(0, len(h), na_radek)]
    return "[\n" + "\n".join(radky) + "\n]"


def _retezec(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Převod souřadnic do posudku
# ---------------------------------------------------------------------------

def _do_pb(vys: VysledekSil, t: TabulkaSil, L_nosniku: Optional[float]) -> tuple:
    """Tabulka v souřadnicích posudku (x od konce nosníku) + (L, L0)."""
    L0 = float(vys.K.Ltot)
    L = float(L_nosniku) if L_nosniku else L0
    if L < L0 - 1e-9:
        raise ValueError(f"Délka nosníku L = {L:g} m je menší než rozpětí L0 = {L0:g} m.")
    xa = 0.5 * (L - L0)
    cols = [t.x + xa, t.M_max, t.M_min, t.V_max, t.V_min]
    if xa > 1e-9:                         # převislé konce bez zatížení
        cols = [np.concatenate([[0.0], c, [L]]) if i == 0 else
                np.concatenate([[0.0], c, [0.0]]) for i, c in enumerate(cols)]
    return TabulkaSil(*cols), L, L0


def _odstran_dvojice_x(t: TabulkaSil) -> TabulkaSil:
    """Posudek interpoluje np.interp – dvojité x (vnitřní podpora) nahradí
    hodnotou s větší absolutní hodnotou (prostý nosník je nemá)."""
    keep = np.ones(len(t.x), bool)
    for i in range(1, len(t.x)):
        if abs(t.x[i] - t.x[i - 1]) < 1e-9:
            keep[i - 1] = False
            for a, f in (("V_max", max), ("V_min", min)):
                arr = getattr(t, a)
                arr[i] = f(arr[i], arr[i - 1])
    return TabulkaSil(t.x[keep], t.M_max[keep], t.M_min[keep], t.V_max[keep], t.V_min[keep])


# ---------------------------------------------------------------------------
# Sekce [zatizeni] pro Posudek PB
# ---------------------------------------------------------------------------

def toml_zatizeni_pb(vys: VysledekSil, o: int, L_nosniku: Optional[float] = None,
                     rezim: str = "kombinace", msu: str = "6.10ab",
                     t_stale: Optional[float] = None,
                     t_vneseni: Optional[float] = None) -> str:
    """Text sekce [zatizeni] vstupu Posudku PB pro výstup o (0-based).

    rezim: "kombinace" | "zatezovaci_stavy";  msu: "6.10ab" | "6.10".
    t_stale:   stáří nosníku při vnesení g − g0 [dny] (režim zatěžovacích stavů).
    t_vneseni: stáří od kdy působí kvazistálá kombinace [dny] (režim kombinací).
    """
    if rezim not in ("kombinace", "zatezovaci_stavy"):
        raise ValueError("Režim musí být 'kombinace' nebo 'zatezovaci_stavy'.")
    if msu not in ("6.10ab", "6.10"):
        raise ValueError("MSÚ musí být '6.10ab' nebo '6.10'.")
    K, s = vys.K, vys.soucinitele
    pop = vys.popisky[o]
    jm, jv = vys.jednotky
    tg0, L, L0 = _do_pb(vys, vys.tabulka(o, "g0"), L_nosniku)
    hl = [
        f"# ---- Zatížení z BLC {__version__} (vnitřní síly g − g0, q) ----",
        f"# Konstrukce: {vys.popis}",
        f"# Posuzovaný výstup: {pop} (y = {float(vys.vyst.y[o]):.3f} m), jednotky {jm}, {jv}",
        f"# Nosník posudku: L = {L:g} m, L0 = {L0:g} m (x posudku = x od podpory + "
        f"{0.5 * (L - L0):g} m)",
        f"# g0 z BLC = {vys.g0:.3f} {'kN/m²' if vys.deska else 'kN/m'} – posudek počítá g0 "
        f"z průřezu sám (M_g0,max BLC = {tg0.M_max.max():.2f} {jm})",
    ]
    for st in vys.stavy.values():
        hl.append(f"# {st.nazev}: {st.popis}")
    hl.append(f"# Součinitele: γ_G = {s.gamma_G:g}, γ_G,inf = {s.gamma_G_inf:g}, ξ = {s.xi:g}, "
              f"γ_Q = {s.gamma_Q:g}, ψ0 = {s.psi0:g}, ψ1 = {s.psi1:g}, ψ2 = {s.psi2:g} "
              "(pro vozidlo ověřit)")
    for w in vys.varovani:
        hl.append(f"# ! {w}")
    out = hl + ["", "[zatizeni]", f'zpusob = "{rezim}"', "obsahuje_vlastni_tihu = false"]

    if rezim == "kombinace":
        if t_vneseni is not None:
            out.append(f"t_vneseni = {float(t_vneseni):g}")
        druhy = (["6.10a", "6.10b"] if msu == "6.10ab" else ["6.10"]) + \
                ["char", "casta", "kvazistala"]
        for druh in druhy:
            t, _, _ = _do_pb(vys, vys.kombinace(o, druh, vcetne_g0=False), L_nosniku)
            t = _odstran_dvojice_x(t)
            out += ["", "[[zatizeni.kombinace]]", f'druh = "{druh}"',
                    f"nazev = {_retezec('BLC ' + pop + ' – ' + NAZVY_KOMBINACI_PB[druh])}",
                    f"x = {_pole(t.x, 3)}", f"M_max = {_pole(t.M_max)}",
                    f"M_min = {_pole(t.M_min)}", f"V_max = {_pole(t.V_max)}",
                    f"V_min = {_pole(t.V_min)}"]
    else:
        tg, _, _ = _do_pb(vys, vys.tabulka(o, "g-g0"), L_nosniku)
        tg = _odstran_dvojice_x(tg)
        out += ["", "[[zatizeni.stale]]",
                f"nazev = {_retezec('Ostatní stálé g − g0 (BLC ' + pop + ')')}",
                f"gamma = {s.gamma_G:g}", f"gamma_inf = {s.gamma_G_inf:g}"]
        if t_stale is not None:
            out.append(f"t = {float(t_stale):g}")
        out += ["[zatizeni.stale.tabulka]", f"x = {_pole(tg.x, 3)}",
                f"M = {_pole(tg.M_max)}", f"V = {_pole(tg.V_max)}"]
        if "q" in vys.stavy:
            tq, _, _ = _do_pb(vys, vys.tabulka(o, "q"), L_nosniku)
            tq = _odstran_dvojice_x(tq)
            Vq = np.where(np.abs(tq.V_max) >= np.abs(tq.V_min), tq.V_max, tq.V_min)
            out += ["", "[[zatizeni.promenne]]",
                    f"nazev = {_retezec('Pohyblivé q – ' + vys.vozidlo + ' (BLC ' + pop + ')')}",
                    f"psi0 = {s.psi0:g}", f"psi1 = {s.psi1:g}", f"psi2 = {s.psi2:g}",
                    f"gamma = {s.gamma_Q:g}",
                    "[zatizeni.promenne.tabulka]", f"x = {_pole(tq.x, 3)}",
                    f"M = {_pole(tq.M_max)}", f"V = {_pole(Vq)}"]
    text = "\n".join(out) + "\n"
    tomllib.loads(text)                     # kontrola syntaxe
    return text


def zatizeni_pb_dict(vys: VysledekSil, o: int, L_nosniku: Optional[float] = None,
                     rezim: str = "kombinace", msu: str = "6.10ab",
                     t_stale: Optional[float] = None,
                     t_vneseni: Optional[float] = None) -> dict:
    """Sekce [zatizeni] jako slovník – pro parametrickou studii bez souborů:
        d = pb_posudek.vstup.nacti_soubor("nosnik.toml")
        d["zatizeni"] = zatizeni_pb_dict(vys, o, d["nosnik"]["L"])
        model = pb_posudek.vstup.model_ze_slovniku(d)"""
    return tomllib.loads(toml_zatizeni_pb(vys, o, L_nosniku, rezim, msu, t_stale,
                                          t_vneseni))["zatizeni"]


_HLAVICKA = re.compile(r"^\s*\[\[?\s*([A-Za-z0-9_.\-\"' ]+?)\s*\]\]?\s*(#.*)?$")


def vloz_do_vstupu_pb(text_pb: str, fragment: str) -> str:
    """Nahradí ve vstupu posudku (text TOML) všechny sekce [zatizeni…]
    fragmentem; ostatní obsah (včetně komentářů) zůstane."""
    out, v_zat = [], False
    for radek in text_pb.splitlines():
        m = _HLAVICKA.match(radek)
        if m:
            v_zat = m.group(1).strip().strip("\"'").split(".")[0] == "zatizeni"
        if not v_zat:
            out.append(radek)
    while out and not out[-1].strip():
        out.pop()
    text = "\n".join(out) + "\n\n" + fragment
    tomllib.loads(text)
    return text


# ---------------------------------------------------------------------------
# Uložení všech výsledků
# ---------------------------------------------------------------------------

def _tab_dict(t: TabulkaSil) -> dict:
    return {k: [round(float(v), 4) for v in getattr(t, k)]
            for k in ("x", "M_max", "M_min", "V_max", "V_min")}


def vysledky_json(vys: VysledekSil, o_posudek: int) -> dict:
    K, vyb, s = vys.K, vys.vybaveni, vys.soucinitele
    return {
        "program": f"BLC {__version__} – vnitřní síly",
        "popis": vys.popis,
        "jednotky": {"x": "m", "M": vys.jednotky[0], "V": vys.jednotky[1]},
        "konvence": "kladný M táhne dolní vlákna, V = dM/dx; x od osy první podpory výstupu",
        "konstrukce": {"typ": K.typ, "L": K.L, "N": K.N, "b": K.b, "B": K.B, "Iy": K.Iy,
                       "E": K.E, "h": K.h if K.je_deska else K.h_ekv, "spara": K.spara,
                       "b_s": K.b_s, "Iy_s": K.Iy_s, "alfa": K.alfa, "sikmost": K.sikmost,
                       "k_pod": K.k_pod, "uloz": K.uloz, "k_rot": K.k_rot, "d": K.d},
        "vybaveni": {"chodnik_L": vyb.chodnik_L, "chodnik_P": vyb.chodnik_P,
                     "g_chodnik": vyb.g_chodnik, "g_vozovka": vyb.g_vozovka,
                     "g_zabradli": vyb.g_zabradli, "g_svodidla": vyb.g_svodidla,
                     "liniova": [vars(l) for l in vyb.liniova],
                     "tiha_na_metr": vyb.tiha_na_metr(K.B)},
        "g0": vys.g0, "g_spary": vys.g_spary, "vozidlo": vys.vozidlo, "Ve": vys.Ve,
        "dyn": vys.dyn,
        "y_Ve": vys.y_Ve, "roznos": vys.roz,
        "soucinitele": vars(s),
        "stavy": {k: {"nazev": NAZVY_STAVU[k], "popis": v.popis, "n_stavu": v.n_stavu}
                  for k, v in vys.stavy.items()},
        "varovani": vys.varovani,
        "kontrola": vys.kontrola,
        "posuzovany_vystup": vys.popisky[o_posudek],
        "souhrn": vys.souhrn(),
        "vystupy": {vys.popisky[o]: {"y": float(vys.vyst.y[o]),
                                     "stavy": {k: _tab_dict(vys.tabulka(o, k)) for k in vys.stavy}}
                    for o in range(vys.n_vyst)},
    }


def _csv_cislo(v) -> str:
    return f"{v:.4f}".replace(".", ",") if isinstance(v, float) else str(v)


def uloz_vysledky(vys: VysledekSil, slozka: str, vystup=None, kriterium: str = "M",
                  L_nosniku: Optional[float] = None, rezim: str = "kombinace",
                  msu: str = "6.10ab", pb_vstup: Optional[str] = None,
                  t_stale: Optional[float] = None,
                  t_vneseni: Optional[float] = None) -> List[str]:
    """Uloží výsledky a export do posudku.  vystup = číslo (1-based) / popisek
    posuzovaného výstupu; None = nejzatíženější podle kritéria ("M", "M-", "V").
    pb_vstup: vstup Posudku PB (.toml) – vytvoří se jeho kopie se zatížením z BLC;
    L nosníku se pak vezme ze vstupu posudku.  Vrací seznam vytvořených souborů."""
    os.makedirs(slozka, exist_ok=True)
    o = vys.index(vystup) if vystup is not None else vys.rozhodujici(kriterium)
    pop = vys.popisky[o]
    soubory = []

    p = os.path.join(slozka, "vnitrni_sily.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(vysledky_json(vys, o), f, ensure_ascii=False, indent=1)
    soubory.append(p)

    sh = vys.souhrn()
    p = os.path.join(slozka, "souhrn.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(list(sh[0]))
        for d in sh:
            w.writerow([_csv_cislo(v) for v in d.values()])
    soubory.append(p)

    bezpecny = re.sub(r"[^A-Za-z0-9_.=-]", "_", pop)
    p = os.path.join(slozka, f"{bezpecny}_stavy.csv")
    tabs = {k: vys.tabulka(o, k) for k in vys.stavy}
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        hl = ["x [m]"]
        for k in tabs:
            hl += [f"M_max {k}", f"M_min {k}", f"V_max {k}", f"V_min {k}"]
        w.writerow(hl)
        x = tabs["g0"].x
        for i in range(len(x)):
            r = [float(x[i])]
            for t in tabs.values():
                r += [float(t.M_max[i]), float(t.M_min[i]), float(t.V_max[i]), float(t.V_min[i])]
            w.writerow([_csv_cislo(v) for v in r])
    soubory.append(p)

    text_pb = None
    if pb_vstup:
        with open(pb_vstup, encoding="utf-8-sig") as f:
            text_pb = f.read()
        d = tomllib.loads(text_pb)
        n = d.get("nosnik", {})
        L_pb, L0_pb = n.get("L"), n.get("L0") or n.get("L")
        if L_pb:
            L_nosniku = float(L_pb)
        if L0_pb and abs(float(L0_pb) - vys.K.Ltot) > 0.01:
            vys.varovani.append(f"Rozpětí L0 = {float(L0_pb):g} m ve vstupu posudku se liší "
                                f"od rozpětí BLC {vys.K.Ltot:g} m.")
        zat = d.get("zatizeni", {})
        if t_vneseni is None:
            t_vneseni = zat.get("t_vneseni")
        if t_stale is None:
            stale = zat.get("stale") or [{}]
            t_stale = stale[0].get("t")

    frag = toml_zatizeni_pb(vys, o, L_nosniku, rezim, msu, t_stale, t_vneseni)
    p = os.path.join(slozka, "zatizeni_PB.toml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(frag)
    soubory.append(p)

    if text_pb is not None:
        jmeno = os.path.splitext(os.path.basename(pb_vstup))[0]
        p = os.path.join(slozka, f"{jmeno}_BLC.toml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(vloz_do_vstupu_pb(text_pb, frag))
        soubory.append(p)
    return soubory
