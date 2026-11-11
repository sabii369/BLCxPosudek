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
  stálé        A_dobetonavky [m²] (dobetonávka mezi nosníky → g0, ½ na sousední nosníky, do
               posudku s g − g0), chodnik_L, chodnik_P, g_chodnik, g_vozovka, g_zabradli,
               g_svodidla, g_spary,
               [[blc.liniova]] nazev, g, y, sirka
  chodci       q_chodnik [kN/m²] (zatížení chodníků, obálka; prázdné = podle ČSN 73 6222:
               Vn, Vr 2,5 kN/m², Ve 0), gamma_Qch, psi0_ch, psi1_ch, psi2_ch
  vozidlo      vozidlo = "Vn" | "Vr" | "Ve" | "MLC_k" | "MLC_p", Vn, Vr, Ve [t], MLC (třída),
               dist (kolona; prázdné = jedno vozidlo), dyn (prázdné = podle ČSN 73 6222, kap. 8:
               Ve δ = 1,05, Vr δ1, Vn δ1–δ3), y_vozidla (Ve, MLC; prázdné = osa vozovky; Vn a Vr
               vždy u kraje vozovky u užšího chodníku), roznos, t_voz, krok, ex
  zatížitelnost zatizitelnost = true → místo posouzení hledá Vn, Vr, Ve pro η = 100 % každého
               posudku; zatizitelnost_druhy = "vse" | "vozidlo" | ["Vn", "Ve", …];
               protokol_zatizitelnosti = "souhrn" | "Vn" | "Vr" | "Ve" (jen druh, posudky při jeho
               zatížitelnosti) | "vse" (dávka: souhrn + každý druh zvlášť)
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
from blc.vnitrni_sily import vnitrni_sily, polohy_q, Soucinitele, VysledekSil, NAZVY_STAVU

VOZIDLA = {"Vn": "Vn – normální zatížitelnost", "Vr": "Vr – výhradní zatížitelnost",
           "Ve": "Ve – výjimečná zatížitelnost", "MLC_k": "MLC kolové", "MLC_p": "MLC pásové"}

VYCHOZI_BLC = {
    "typ_konstrukce": "nosniky", "N": 10, "b": 1.0, "prurez_z_posudku": True,
    "nu": 0.2, "d": 0.5, "spara": False, "alfa": 90.0, "sikmost": "prava", "k_v": 2000.0,
    "uloz": "tvrde", "spoj": "kloub",
    "chodnik_L": 1.5, "chodnik_P": 1.5, "g_chodnik": 5.0, "g_vozovka": 2.6,
    "g_zabradli": 0.5, "g_svodidla": 0.6, "g_spary": 0.0,
    "A_dobetonavky": 0.0,
    "vozidlo": "Ve", "Vn": 32.0, "Vr": 60.0, "Ve": 80.0, "MLC": "MLC80", "dyn": None,
    "roznos": True, "t_voz": 0.0, "krok": 0.25, "ex": 0.125,
    "vystup": "auto", "kriterium": "M", "rezim": "kombinace",
    "gamma_Q": 1.35, "psi0": 0.75, "psi1": 0.75, "psi2": 0.0,
    "q_chodnik": None, "gamma_Qch": 1.35, "psi0_ch": 0.75, "psi1_ch": 0.75, "psi2_ch": 0.0,
    "zatizitelnost": False, "zatizitelnost_druhy": "vse",
    "protokol_zatizitelnosti": "souhrn",
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
        kw.update(A_nosniku=A, Iy=Iy, A_dobetonavky=_f(b.get("A_dobetonavky")) or 0.0)
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
    if voz in ("Ve", "Vn", "Vr"):
        if not _f(b.get(voz)) or float(b[voz]) <= 0:
            raise ValueError(f"Zadejte tíhu vozidla {voz} > 0 [t].")
        kw[voz] = float(b[voz])
    elif voz in ("MLC_k", "MLC_p"):
        kw.update(MLC=b["MLC"], typ_MLC="k" if voz == "MLC_k" else "p", dist=_f(b.get("dist")))
    else:
        raise ValueError(f"Neznámé vozidlo '{voz}' (Vn, Vr, Ve, MLC_k, MLC_p).")
    kw.update(dyn=_f(b.get("dyn")), y_Ve=_f(b.get("y_vozidla")) if voz not in ("Vn", "Vr") else None,
              roznos=bool(b["roznos"]), t_voz=float(b["t_voz"]), krok=float(b["krok"]),
              ex=float(b["ex"]), q_chodnik=_f(b.get("q_chodnik")))
    ns = nastaveni_posudku(d)
    kw["soucinitele"] = Soucinitele(gamma_G=float(ns["gamma_G"]),
                                    gamma_G_inf=float(ns["gamma_G_inf"]), xi=float(ns["xi"]),
                                    gamma_Q=float(b["gamma_Q"]), psi0=float(b["psi0"]),
                                    psi1=float(b["psi1"]), psi2=float(b["psi2"]),
                                    gamma_Qch=float(b["gamma_Qch"]), psi0_ch=float(b["psi0_ch"]),
                                    psi1_ch=float(b["psi1_ch"]), psi2_ch=float(b["psi2_ch"]))
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
    """Vloží do protokolu posudku kapitolu zatížení a vnitřních sil z modelu mostu
    (před kapitolu Zatížení a časová osa): popis stavů, zatížení na mostě, součinitele,
    vnitřní síly na nosnících od jednotlivých stavů a kombinace po nosnících."""
    from pb_posudek.protokol import Kapitola, fmt
    from .grafy_most import GRAFY_ZATIZENI, GRAFY_Q, GRAF_SILY, rezy_posudku
    jm, jv = vys.jednotky
    vyst = "pás" if vys.deska else "nosník"
    K = Kapitola("Zatížení z modelu mostu (BLC)", 2)
    K.text(f"Vnitřní síly od zatěžovacích stavů byly spočteny na modelu celého mostu: {vys.popis}. "
           f"Posuzuje se {vyst} {vys.popisky[o]} (y = {fmt(float(vys.vyst.y[o]))} m).")
    for s in vys.stavy.values():
        K.text(f"{NAZVY_STAVU[s.nazev]}: {s.popis}.")
    if vys.g0_dobetonavka is not None:
        K.text(f"Vlastní tíhu nosníku počítá posudek z průřezu; tíha dobetonávky mezi nosníky "
               f"({fmt(vys.g_dobetonavky)} kN/m, každý nosník nese polovinu sousední dobetonávky, "
               "krajní nosník jen jednu polovinu) průřez nezahrnuje, a proto se do posudku předává "
               "spolu s ostatním stálým zatížením g − g0.")
    if vys.varovani:
        K.text("Upozornění: " + " ".join(vys.varovani))
    # zatížení na mostě
    b = getattr(model, "blc", None)
    if b:
        rz = rezy_posudku(model)
        xs, xp = fmt(model.x[rz["stred"][0]]), fmt(model.x[rz["podpora"][0]])
        K.text(f"Zatížení na mostě; posuzovaný {vyst} je vyznačen oranžově, řezy posudku „střed“ "
               f"(x = {xs} m) a „podpora“ (x = {xp} m, nejblíže vzdálenosti d od osy ložiska) "
               "červeně. Pohyblivé zatížení je zobrazeno v poloze s největším ohybovým momentem ve "
               "středu rozpětí a s největší posouvající silou u podpory (polohy z výpočtu obálky; "
               "u schématu Vn nápravy v pruzích a rovnoměrné zatížení – světle – v nepříznivých "
               "částech plochy vlivu).")
        for p in b["polohy"].values():
            K.text(p.popis + ".")
        for k, nazev in GRAFY_ZATIZENI.items():
            if k not in GRAFY_Q or b["polohy"]:
                K.obrazek(k, nazev)
    # součinitele
    s = vys.soucinitele
    druhy = [("char", "charakteristická"), ("casta", "častá"), ("kvazistala", "kvazistálá"),
             ("6.10a", "MSÚ 6.10a"), ("6.10b", "MSÚ 6.10b"), ("6.10", "MSÚ 6.10")]
    skup = ["G"] + [k for k in ("qch", "q") if k in vys.stavy]
    nazvy_skup = {"G": "g0 + (g − g0)", "qch": "q – chodci", "q": "q – doprava"}
    rows = []
    for druh, naz in druhy:
        r = [naz]
        for sk in skup:
            g, p = s.gama_psi(sk, druh)
            r += [fmt(g, 2), fmt(p, 2)]
        rows.append(r)
    hl = ["Kombinace"]
    for sk in skup:
        hl += [f"γ ({nazvy_skup[sk]})", f"ψ ({nazvy_skup[sk]})"]
    K.tabulka(hl, rows, "Dílčí součinitele γ a součinitele kombinace ψ (u stálých v 6.10b ψ = ξ; "
                        f"příznivé stálé γ_G,inf = {fmt(s.gamma_G_inf, 2)}); účinek = Σ γ·ψ·E, "
                        "proměnná zatížení působí současně")
    K.text("Pozn.: γ_G a ξ jsou převzaty z nastavení posouzení, γ a ψ proměnných zatížení ze zadání "
           "mostu (pro zatížitelnost Vn, Vr, Ve udává ČSN 73 6222, čl. 10.1.1 a 10.2.1, ψ0 = ψ1 = "
           "0,75; γ podle ČSN EN 1990); pro vozidla MLC je nutné je ověřit.")
    # vnitřní síly od stavů
    K.obrazek(GRAF_SILY[0], GRAF_SILY[1])
    stavy = list(vys.stavy)
    rows = []
    for i, dd in enumerate(vys.souhrn()):
        rows.append([dd["vystup"] + (" ◄" if i == o else ""), fmt(dd["y"])] +
                    [fmt(dd["M_" + k]) for k in stavy] + [fmt(dd["V_" + k]) for k in stavy])
    kr = {"g0": "g0", "g-g0": "g − g0", "qch": "chodci", "q": "doprava"}
    K.tabulka([vyst.capitalize(), "y [m]"] + [f"max M {kr[k]} [{jm}]" for k in stavy] +
              [f"max |V| {kr[k]} [{jv}]" for k in stavy], rows,
              f"Maxima vnitřních sil po nosnících od jednotlivých zatěžovacích stavů; ◄ = posuzovaný")
    # kombinace po nosnících
    K.text("Vnitřní síly kombinací po nosnících – extrémy po délce nosníku; kombinace obsahují "
           "vlastní tíhu g0 z modelu mostu, ostatní stálé g − g0 a proměnná zatížení podle tabulky "
           "součinitelů.")
    for druh, naz in druhy:
        rows = []
        for i, dd in enumerate(vys.extremy_kombinace(druh, vcetne_g0=True)):
            rows.append([dd["vystup"] + (" ◄" if i == o else ""), fmt(dd["M_max"]),
                         fmt(dd["x_M_max"], 2), fmt(dd["M_min"]), fmt(dd["V_max"]), fmt(dd["V_min"])])
        K.tabulka([vyst.capitalize(), f"max M [{jm}]", "x (max M) [m]", f"min M [{jm}]",
                   f"max V [{jv}]", f"min V [{jv}]"], rows, f"Kombinace {naz} – vnitřní síly po nosnících")
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
    model.blc = dict(vys=vys, o=o, polohy=polohy_q(vys, o))
    kapitola_blc(model, vys, o)
    from .grafy_most import vloz_do_protokolu
    vloz_do_protokolu(model)
    return vys, o, model


def uloz_protokol_most(model, adresar="vystup", embed: bool = True):
    """HTML protokol posudku včetně grafů zatížení mostu (kapitola BLC)."""
    import json
    from pathlib import Path
    from pb_posudek.grafy import vykresli_vse
    from pb_posudek.report import sestav_html
    from .grafy_most import vykresli_most
    adr = Path(adresar)
    adr.mkdir(parents=True, exist_ok=True)
    adr_obr = adr / "obrazky"
    if not model.protokol.posudky:
        model.spocitej()
    obr = vykresli_vse(model, adr_obr)
    if getattr(model, "blc", None):
        obr.update(vykresli_most(model, adr_obr))
    out = adr / "protokol.html"
    out.write_text(sestav_html(model, obr, adr_obr, embed), encoding="utf-8")
    vys = dict(
        projekt=model.projekt,
        posudky=[v.as_dict() for v in model.protokol.posudky],
        x=model.x.tolist(),
        faze=[dict(nazev=f.nazev, t=f.t, P_kN=(-model._sily_predpeti(f.sigma)[0]).tolist(),
                   sigma_p=[s.tolist() for s in f.sigma]) for f in model.faze],
    )
    (adr / "vysledky.json").write_text(json.dumps(vys, ensure_ascii=False, indent=1, default=float),
                                       encoding="utf-8")
    return out
