"""Načtení vstupních dat z TOML / JSON souboru nebo slovníku."""
from __future__ import annotations

import json
import tomllib
from dataclasses import fields
from pathlib import Path

from .kabel import Kabel, geometrie_parabola, geometrie_polygon, geometrie_primka
from .materialy import Beton, BetonarskaVyztuz, PredpinaciVyztuz
from .model import Nastaveni, NosnikPB, SmykovaVyztuz
from .msu import VrstvaVyztuze
from .prurez import Prurez
from .zatizeni import KombinaceVstup, ZatezovaciStav


def nacti_soubor(cesta: str | Path) -> dict:
    cesta = Path(cesta)
    if cesta.suffix.lower() == ".json":
        return json.loads(cesta.read_text(encoding="utf-8"))
    with open(cesta, "rb") as f:
        return tomllib.load(f)


def _vyber(d: dict, cls) -> dict:
    jmena = {f.name for f in fields(cls) if f.init}
    return {k: v for k, v in d.items() if k in jmena}


def _prurez(d: dict) -> Prurez:
    kw = dict(nazev=d.get("nazev", ""), obvod_vysychani=d.get("obvod_vysychani"))
    if "vrstvy" in d:
        return Prurez.z_vrstev([tuple(v) for v in d["vrstvy"]], **kw)
    if "obrys" in d:
        return Prurez(d["obrys"], otvory=d.get("otvory", []), **kw)
    if "b" in d and "h" in d:
        return Prurez.obdelnik(d["b"], d["h"], **kw)
    raise ValueError("Průřez: zadejte 'vrstvy', 'obrys' nebo 'b' a 'h'.")


_POVINNE_KABEL = {"parabola": ("z_L", "z_S"), "polygon": ("body",), "primka": ("z_L",)}


def _kabel(d: dict, L: float, vyztuz: PredpinaciVyztuz, i: int) -> Kabel:
    typ = d.get("geometrie", "parabola")
    chybi = [k for k in _POVINNE_KABEL.get(typ, ()) + ("pocet_lan", "sigma_max") if d.get(k) in (None, "", [])]
    if chybi:
        raise ValueError(f"Kabel {d.get('nazev', i + 1)} (geometrie {typ}): chybí {', '.join(chybi)}")
    if typ == "parabola":
        g = geometrie_parabola(L, d["z_L"], d["z_S"], d.get("z_P", d["z_L"]), d.get("x_S"))
        popis = f"parabola z = {d['z_L']} / {d['z_S']} / {d.get('z_P', d['z_L'])} mm"
    elif typ == "polygon":
        g = geometrie_polygon([tuple(b) for b in d["body"]], d.get("polomery"))
        popis = f"polygon ({len(d['body'])} bodů" + (", zaoblení R" if d.get("polomery") else "") + ")"
    elif typ == "primka":
        g = geometrie_primka(L, d["z_L"], d.get("z_P"))
        popis = f"přímka z = {d['z_L']}" + (f" → {d['z_P']}" if d.get("z_P") is not None else "") + " mm"
    else:
        raise ValueError(f"Neznámá geometrie kabelu: {typ}")
    return Kabel(
        nazev=d.get("nazev", f"K{i + 1}"), pocet_lan=int(d["pocet_lan"]), vyztuz=vyztuz, geometrie=g,
        sigma_max=float(d["sigma_max"]), napinani=d.get("napinani", "levy"), mu=d.get("mu", 0.19),
        k=d.get("k", 0.005), pokluz=d.get("pokluz", 6.0), d_kanalku=d.get("d_kanalku", 0.0),
        popis_geometrie=popis,
    )


def _zs(d: dict, druh: str, L: float) -> ZatezovaciStav:
    rov = []
    if "q" in d:
        rov.append((float(d["q"]), float(d.get("od", 0.0)), float(d.get("do", L))))
    for r in d.get("rovnomerne", []):
        rov.append(tuple(float(v) for v in r))
    poh = None
    if "pohyblive" in d:
        poh = (list(d["pohyblive"]["sily"]), list(d["pohyblive"].get("rozestupy", [])))
    tab = None
    if "tabulka" in d:
        t = d["tabulka"]
        tab = (t["x"], t["M"], t.get("V", [0.0] * len(t["x"])))
    return ZatezovaciStav(
        nazev=d.get("nazev", druh), druh=druh, t=d.get("t"), rovnomerne=rov,
        bremena=[tuple(b) for b in d.get("bremena", [])], pohyblive=poh, tabulka=tab,
        psi0=d.get("psi0", 0.0), psi1=d.get("psi1", 0.0), psi2=d.get("psi2", 0.0),
        gamma=d.get("gamma", 1.35 if druh == "stale" else 1.5), gamma_inf=d.get("gamma_inf", 1.0),
        skupina=d.get("skupina", ""),
    )


def _kombinace(d: dict) -> KombinaceVstup:
    if "druh" not in d:
        raise ValueError("Kombinace: chybí 'druh' (6.10a, 6.10b, 6.10, char, casta, kvazistala).")
    tab = {k: d.get(k) for k in ("x", "M_max", "M_min", "V_max", "V_min")}
    if tab["x"] is not None:
        n = len(tab["x"])
        for k, v in tab.items():
            if v is not None and len(v) != n:
                raise ValueError(f"Kombinace {d['druh']}: sloupec {k} má {len(v)} hodnot, x má {n}.")
        if tab["M_max"] is None:
            raise ValueError(f"Kombinace {d['druh']}: tabulka musí obsahovat M_max.")
    elif d.get("q") is None and not d.get("bremena"):
        raise ValueError(f"Kombinace {d['druh']}: zadejte q, břemena nebo tabulku x / M_max / V_max.")
    return KombinaceVstup(druh=str(d["druh"]), q=d.get("q"), od=d.get("od"), do=d.get("do"),
                          bremena=[tuple(b) for b in d.get("bremena", [])], nazev=d.get("nazev", ""), **tab)


def model_ze_slovniku(d: dict) -> NosnikPB:
    beton = Beton(**{**_vyber(d.get("beton", {}), Beton),
                     **({"Ecm_zadany": d["beton"]["Ecm"]} if "Ecm" in d.get("beton", {}) else {})})
    predp = PredpinaciVyztuz(**_vyber(d.get("predpinaci_vyztuz", {}), PredpinaciVyztuz))
    bet = BetonarskaVyztuz(**_vyber(d.get("betonarska_vyztuz", {}), BetonarskaVyztuz))
    prurez = _prurez(d["prurez"])
    n = d.get("nosnik", {})
    L = float(n["L"])
    kabely = [_kabel(k, L, predp, i) for i, k in enumerate(d.get("kabel", []))]
    vyz = [VrstvaVyztuze(float(v["z"]), float(v["As"]), v.get("nazev", "")) for v in d.get("vyztuz", [])]
    smyk = [SmykovaVyztuz(**_vyber(s, SmykovaVyztuz)) for s in d.get("smykova_vyztuz", [])]
    pr = d.get("prostredi", {})
    co = d.get("casova_osa", {})
    zat = d.get("zatizeni", {})
    zpusob = zat.get("zpusob", "kombinace" if zat.get("kombinace") else "zatezovaci_stavy")
    if zpusob == "kombinace":
        stale, prom = [], []
        komb = [_kombinace(k) for k in zat.get("kombinace", [])]
        if not komb:
            raise ValueError("Zatížení: způsob 'kombinace', ale nejsou zadány žádné kombinace.")
    else:
        stale = [_zs(z, "stale", L) for z in zat.get("stale", [])]
        prom = [_zs(z, "promenne", L) for z in zat.get("promenne", [])]
        komb = []
    nast = Nastaveni(**_vyber(d.get("posouzeni", {}), Nastaveni))
    pd = d.get("predem", {})
    return NosnikPB(
        beton=beton, predpinaci=predp, betonarska=bet, prurez=prurez, L=L, L0=n.get("L0"),
        kabely=kabely, typ_predpeti=n.get("predpeti", "dodatecne"), vyztuz=vyz, smykova=smyk,
        RH=pr.get("RH", 70.0), t_s=pr.get("t_s", 3.0), t0=co.get("t0", 7.0),
        t_provoz=co.get("t_provoz", 120.0), t_konec=co.get("t_konec", 36500.0), stale=stale,
        promenne=prom, nastaveni=nast, projekt=d.get("projekt", {}), n_rezu=n.get("pocet_rezu", 41),
        charakteristiky=n.get("charakteristiky", "brutto"), pocet_napinani=n.get("pocet_napinani"),
        relaxace_pred_uvolnenim_h=pd.get("relaxace_pred_uvolnenim_h"),
        predem_eta_p1=pd.get("eta_p1", 3.2), predem_alpha1=pd.get("alpha1", 1.25),
        predem_alpha2=pd.get("alpha2", 0.19), kombinace_vstup=komb,
        kombinace_vcetne_g0=bool(zat.get("obsahuje_vlastni_tihu", False)), t_vneseni=zat.get("t_vneseni"),
    )


def nacti_model(cesta: str | Path) -> NosnikPB:
    return model_ze_slovniku(nacti_soubor(cesta))
