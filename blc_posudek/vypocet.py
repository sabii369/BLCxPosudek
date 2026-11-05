"""
vypocet.py
==========
Spojený výpočet: vnitřní síly mostu (BLC) → zatížení nosníku → posudek PB.

Vstupní data jsou vstupní soubor Posudku PB (TOML/JSON) rozšířený o sekci [blc]
(most, vybavení, vozidlo).  Sekce [zatizeni] se NEZADÁVÁ – vytvoří se z obálek
vnitřních sil vybraného nosníku (nejzatíženějšího nebo zadaného).

Převzato z posudku (jedno zadání pro oba výpočty):
  rozpětí L0 a délka nosníku L       [nosnik]
  třída betonu, objemová tíha         [beton]          → E nosníků, γ_b pro g0
  A a Iy nosníku                      [prurez]         (blc.prurez_z_posudku = true)
  γ_G, γ_G,inf, ξ, kombinace MSÚ      [posouzeni]
Sekce [blc]:
  konstrukce   typ_konstrukce, N, b, h, A_nosniku, Iy, prurez_z_posudku, nu, d, spara, b_s,
               Iy_s, beton_s, alfa, sikmost, k_v [MN/m/m], uloz, k_rot [MNm/rad/m], spoj
  stálé        chodnik_L, chodnik_P, g_chodnik, g_vozovka, g_zabradli, g_svodidla, g_spary,
               [[blc.liniova]] nazev, g, y, sirka
  vozidlo      vozidlo = "Ve" | "MLC_k" | "MLC_p", Ve [t], MLC (třída), dist (kolona; prázdné =
               jedno vozidlo), dyn, y_vozidla (prázdné = osa vozovky), roznos, t_voz, krok, ex
  předání      vystup ("auto" | "N3"), kriterium ("M" | "M-" | "V"), rezim ("kombinace" |
               "zatezovaci_stavy"), gamma_Q, psi0, psi1, psi2, t_vneseni, t_stale
"""

from __future__ import annotations
import copy
import tomllib
from dataclasses import fields
from typing import Optional

from blc.export_pb import zatizeni_pb_dict
from blc.stale_zatizeni import Vybaveni, LiniovaZatizeni
from blc.vnitrni_sily import vnitrni_sily, Soucinitele, VysledekSil, NAZVY_STAVU

VOZIDLA = {"Ve": "Ve – výjimečná zatížitelnost", "MLC_k": "MLC kolové", "MLC_p": "MLC pásové"}

VYCHOZI_BLC = {
    "typ_konstrukce": "nosniky", "N": 10, "b": 1.0, "prurez_z_posudku": True,
    "nu": 0.2, "d": 0.5, "spara": False, "alfa": 90.0, "sikmost": "prava", "k_v": 2000.0,
    "uloz": "tvrde", "spoj": "kloub",
    "chodnik_L": 1.5, "chodnik_P": 1.5, "g_chodnik": 5.0, "g_vozovka": 2.6,
    "g_zabradli": 0.5, "g_svodidla": 0.6, "g_spary": 0.0,
    "vozidlo": "Ve", "Ve": 80.0, "MLC": "MLC80", "dyn": 1.0, "roznos": True, "t_voz": 0.0,
    "krok": 0.25, "ex": 0.125,
    "vystup": "auto", "kriterium": "M", "rezim": "kombinace",
    "gamma_Q": 1.35, "psi0": 0.75, "psi1": 0.75, "psi2": 0.0,
}


def nacti(cesta: str) -> dict:
    with open(cesta, encoding="utf-8-sig") as f:
        text = f.read()
    if str(cesta).lower().endswith(".json"):
        import json
        return json.loads(text)
    return tomllib.loads(text)


def vlastnosti_prurezu(d: dict) -> tuple[float, float]:
    """(A [m²], Iy [m⁴]) brutto průřezu posudku ([prurez], mm)."""
    from pb_posudek.vstup import _prurez
    p = _prurez(d["prurez"])
    return p.A * 1e-6, p.I * 1e-12


def nastaveni_posudku(d: dict) -> dict:
    """γ_G, γ_G,inf, ξ, kombinace MSÚ z [posouzeni] (s výchozími hodnotami posudku)."""
    from pb_posudek.model import Nastaveni
    n = {f.name: f.default for f in fields(Nastaveni)}
    n.update({k: v for k, v in d.get("posouzeni", {}).items() if k in n})
    return n


def _f(v) -> Optional[float]:
    return None if v in (None, "") else float(v)


def parametry_blc(d: dict) -> dict:
    """Argumenty funkce blc.vnitrni_sily ze spojených vstupních dat."""
    b = {**VYCHOZI_BLC, **d.get("blc", {})}
    n = d.get("nosnik", {})
    if "L" not in n:
        raise ValueError("Zadejte délku nosníku L (karta Nosník a předpětí).")
    L0 = float(n.get("L0") or n["L"])
    beton = d.get("beton", {})
    deska = b["typ_konstrukce"] == "deska"
    kw = dict(L=L0, typ_konstrukce=b["typ_konstrukce"], nu=float(b["nu"]), d=float(b["d"]),
              alfa=float(b["alfa"]), sikmost=b["sikmost"], uloz=b["uloz"], spoj=b["spoj"],
              b=float(b["b"]), tisk=False)
    if beton.get("Ecm"):
        kw["E"] = float(beton["Ecm"])
    else:
        kw["beton"] = beton.get("trida", "C35/45")
    kw["gamma_beton"] = float(beton.get("objemova_tiha", 25.0))
    kv, kr = _f(b.get("k_v")), _f(b.get("k_rot"))
    kw["k_pod"] = kv * 1000.0 if kv else None
    kw["k_rot"] = kr * 1000.0 if kr else None
    if deska:
        if not _f(b.get("h")):
            raise ValueError("Deska: zadejte tloušťku h.")
        kw.update(h=float(b["h"]), N=1)
    else:
        kw["N"] = int(b["N"])
        if b.get("prurez_z_posudku", True):
            A, Iy = vlastnosti_prurezu(d)
        else:
            A, Iy = _f(b.get("A_nosniku")), _f(b.get("Iy"))
            if not Iy:
                raise ValueError("Zadejte Iy nosníku (nebo převzetí z průřezu posudku).")
        kw.update(A_nosniku=A, Iy=Iy)
        if b.get("spara"):
            kw.update(spara=True, b_s=float(b["b_s"]), Iy_s=float(b["Iy_s"]),
                      g_spary=float(b.get("g_spary") or 0.0))
            if b.get("beton_s"):
                kw["beton_s"] = b["beton_s"]
    kw["vybaveni"] = Vybaveni(
        chodnik_L=float(b["chodnik_L"]), chodnik_P=float(b["chodnik_P"]),
        g_chodnik=float(b["g_chodnik"]), g_vozovka=float(b["g_vozovka"]),
        g_zabradli=float(b["g_zabradli"]), g_svodidla=float(b["g_svodidla"]),
        liniova=[LiniovaZatizeni(l.get("nazev", f"liniové {i + 1}"), float(l["g"]), float(l["y"]),
                                 float(l.get("sirka", 0.2)))
                 for i, l in enumerate(b.get("liniova", []))])
    voz = b["vozidlo"]
    if voz == "Ve":
        kw["Ve"] = float(b["Ve"])
    elif voz in ("MLC_k", "MLC_p"):
        kw.update(MLC=b["MLC"], typ_MLC="k" if voz == "MLC_k" else "p", dist=_f(b.get("dist")))
    else:
        raise ValueError(f"Neznámé vozidlo '{voz}' (Ve, MLC_k, MLC_p).")
    kw.update(dyn=float(b["dyn"]), y_Ve=_f(b.get("y_vozidla")), roznos=bool(b["roznos"]),
              t_voz=float(b["t_voz"]), krok=float(b["krok"]), ex=float(b["ex"]))
    ns = nastaveni_posudku(d)
    kw["soucinitele"] = Soucinitele(gamma_G=float(ns["gamma_G"]),
                                    gamma_G_inf=float(ns["gamma_G_inf"]), xi=float(ns["xi"]),
                                    gamma_Q=float(b["gamma_Q"]), psi0=float(b["psi0"]),
                                    psi1=float(b["psi1"]), psi2=float(b["psi2"]))
    return kw


def vyber_nosnik(vys: VysledekSil, d: dict) -> int:
    """Posuzovaný výstup (0-based): zadaný, nebo nejzatíženější podle kritéria."""
    b = {**VYCHOZI_BLC, **d.get("blc", {})}
    v = str(b.get("vystup") or "auto")
    if v != "auto" and v in vys.popisky:
        return vys.popisky.index(v)
    return vys.rozhodujici(b.get("kriterium", "M"))


def zatizeni_z_blc(vys: VysledekSil, d: dict, o: Optional[int] = None) -> dict:
    """Sekce [zatizeni] posudku z obálek výstupu o (výchozí podle [blc])."""
    b = {**VYCHOZI_BLC, **d.get("blc", {})}
    o = vyber_nosnik(vys, d) if o is None else o
    ns = nastaveni_posudku(d)
    n = d.get("nosnik", {})
    t_v = _f(b.get("t_vneseni"))
    t_s = _f(b.get("t_stale"))
    if t_s is None:
        t_s = t_v if t_v is not None else _f(d.get("casova_osa", {}).get("t_provoz"))
    return zatizeni_pb_dict(vys, o, float(n["L"]), b.get("rezim", "kombinace"),
                            ns.get("kombinace_msu", "6.10ab"), t_s, t_v)


def data_pro_posudek(vys: VysledekSil, d: dict, o: Optional[int] = None) -> dict:
    """Kopie vstupních dat s [zatizeni] z obálek BLC (bez sekce [blc])."""
    out = {k: copy.deepcopy(v) for k, v in d.items() if k != "blc"}
    out["zatizeni"] = zatizeni_z_blc(vys, d, o)
    return out


def kapitola_blc(model, vys: VysledekSil, o: int) -> None:
    """Vloží do protokolu posudku kapitolu o původu zatížení (před kapitolu Zatížení)."""
    from pb_posudek.protokol import Kapitola, fmt
    jm, jv = vys.jednotky
    K = Kapitola("Zatížení z modelu mostu (BLC)", 2)
    K.text(f"Vnitřní síly od zatěžovacích stavů vlastní tíhy g0, ostatního stálého zatížení g − g0 "
           f"a pohyblivého zatížení q byly spočteny na modelu celého mostu: {vys.popis}. "
           f"Posuzuje se {'pás' if vys.deska else 'nosník'} {vys.popisky[o]} "
           f"(y = {fmt(float(vys.vyst.y[o]))} m).")
    for s in vys.stavy.values():
        K.text(f"{NAZVY_STAVU[s.nazev]}: {s.popis}.")
    if vys.varovani:
        K.text("Upozornění: " + " ".join(vys.varovani))
    s = vys.soucinitele
    K.text(f"Do posudku jsou převzaty obálky g − g0 a q (vlastní tíhu nosníku g0 počítá posudek "
           f"z průřezu; g0 v modelu mostu = {fmt(vys.g0)} {'kN/m²' if vys.deska else 'kN/m'}). "
           f"Součinitele: γ_G = {fmt(s.gamma_G)}, ξ = {fmt(s.xi)}, γ_Q = {fmt(s.gamma_Q)}, "
           f"ψ0 = {fmt(s.psi0)}, ψ1 = {fmt(s.psi1)}, ψ2 = {fmt(s.psi2)}.")
    stavy = list(vys.stavy)
    rows = []
    for i, dd in enumerate(vys.souhrn()):
        rows.append([dd["vystup"] + (" ◄" if i == o else ""), fmt(dd["y"])] +
                    [fmt(dd["M_" + k]) for k in stavy] + [fmt(dd["V_" + k]) for k in stavy] +
                    [fmt(dd["M_Ed"]), fmt(dd["V_Ed"])])
    K.tabulka(["Výstup", "y [m]"] + [f"max M {k} [{jm}]" for k in stavy] +
              [f"max |V| {k} [{jv}]" for k in stavy] + [f"M_Ed [{jm}]", f"V_Ed [{jv}]"], rows,
              "Maxima vnitřních sil po nosnících (M_Ed, V_Ed: MSÚ 6.10 včetně g0); ◄ = posuzovaný")
    kap = model.protokol.kapitoly
    i = next((j for j, k in enumerate(kap) if k.nazev.startswith("Zatížení")), len(kap))
    kap.insert(i, K)


def spocti(d: dict, vys: Optional[VysledekSil] = None, o: Optional[int] = None):
    """Celý výpočet: BLC (není-li dodán vys) → posudek PB.  Vrací (vys, o, model)."""
    from pb_posudek.vstup import model_ze_slovniku
    if vys is None:
        vys = vnitrni_sily(**parametry_blc(d))
    o = vyber_nosnik(vys, d) if o is None else o
    model = model_ze_slovniku(data_pro_posudek(vys, d, o))
    model.spocitej()
    kapitola_blc(model, vys, o)
    return vys, o, model
