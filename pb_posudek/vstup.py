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
from .protokol import cislo
from .prurez import Prurez
from .teplota import Teplota
from .zatizeni import KombinaceVstup, ZatezovaciStav


def nacti_soubor(cesta: str | Path) -> dict:
    cesta = Path(cesta)
    text = cesta.read_text(encoding="utf-8-sig")  # i soubory s BOM (Poznámkový blok)
    if cesta.suffix.lower() == ".json":
        return json.loads(text)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Chyba v zápisu souboru {cesta.name}: {e}") from e


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


def geometrie_kabelu(d: dict, L: float, i: int = 0, povinne: tuple = ()):
    """Geometrie kabelu ze slovníku vstupu → (geometrie, popis). Používá ji i náhled v GUI."""
    typ = d.get("geometrie", "parabola")
    chybi = [k for k in _POVINNE_KABEL.get(typ, ()) + povinne if d.get(k) in (None, "", [])]
    if chybi:
        raise ValueError(f"Kabel {d.get('nazev', i + 1)} (geometrie {typ}): chybí {', '.join(chybi)}")
    if typ == "parabola":
        g = geometrie_parabola(L, d["z_L"], d["z_S"], d.get("z_P", d["z_L"]), d.get("x_S"))
        popis = f"parabola z = {cislo(d['z_L'])} / {cislo(d['z_S'])} / {cislo(d.get('z_P', d['z_L']))} mm"
    elif typ == "polygon":
        g = geometrie_polygon([tuple(b) for b in d["body"]], d.get("polomery"))
        popis = f"polygon ({len(d['body'])} bodů" + (", zaoblení R" if d.get("polomery") else "") + ")"
    elif typ == "primka":
        g = geometrie_primka(L, d["z_L"], d.get("z_P"))
        popis = f"přímka z = {cislo(d['z_L'])}" + (f" → {cislo(d['z_P'])}" if d.get("z_P") is not None else "") + " mm"
    else:
        raise ValueError(f"Neznámá geometrie kabelu: {typ}")
    return g, popis


def postup_napinani(v, kde: str = "") -> list[tuple[float, float]]:
    """Postup napínání [[napětí na lisu MPa, doba podržení min], …] (doba lze vynechat)."""
    if not v:
        return []
    out = []
    for krok in v:
        hodn = list(krok) if isinstance(krok, (list, tuple)) else [krok]
        if not 1 <= len(hodn) <= 2:
            raise ValueError(f"{kde}postup napínání: krok {krok} – zadejte [napětí, doba podržení].")
        sg, tm = float(hodn[0]), float(hodn[1]) if len(hodn) > 1 else 0.0
        if sg < 0 or tm < 0:
            raise ValueError(f"{kde}postup napínání: napětí ani doba podržení nesmí být záporné.")
        out.append((sg, tm))
    return out


def _kabel(d: dict, L: float, vyztuz: PredpinaciVyztuz, i: int, postup_vychozi=None) -> Kabel:
    g, popis = geometrie_kabelu(d, L, i, povinne=("pocet_lan", "sigma_max"))
    nazev = d.get("nazev", f"K{i + 1}")
    postup = postup_napinani(d["postup"] if "postup" in d else postup_vychozi, f"Kabel {nazev}: ")
    return Kabel(
        nazev=nazev, pocet_lan=int(d["pocet_lan"]), vyztuz=vyztuz, geometrie=g, postup=postup,
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
    dp = dict(d.get("predpinaci_vyztuz", {}))
    if "eps_uk" in dp and "taznost" not in dp:  # starší zápis: ε_uk jako poměrné číslo
        dp["taznost"] = float(dp["eps_uk"]) * 1e3
    predp = PredpinaciVyztuz(**_vyber(dp, PredpinaciVyztuz))
    bet = BetonarskaVyztuz(**_vyber(d.get("betonarska_vyztuz", {}), BetonarskaVyztuz))
    prurez = _prurez(d["prurez"])
    n = d.get("nosnik", {})
    L = float(n["L"])
    kabely = [_kabel(k, L, predp, i, n.get("postup_napinani")) for i, k in enumerate(d.get("kabel", []))]
    vyz = [VrstvaVyztuze(float(v["z"]), float(v["As"]), v.get("nazev", ""),
                         float(v["phi"]) if v.get("phi") not in (None, "") else None) for v in d.get("vyztuz", [])]
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
    deg = d.get("degradace", {})
    return NosnikPB(
        beton=beton, predpinaci=predp, betonarska=bet, prurez=prurez, L=L, L0=n.get("L0"),
        kabely=kabely, typ_predpeti=n.get("predpeti", "dodatecne"), vyztuz=vyz, smykova=smyk,
        RH=pr.get("RH", 70.0), t_s=pr.get("t_s", 3.0), t0=co.get("t0", 7.0),
        t_provoz=co.get("t_provoz", 120.0), t_konec=co.get("t_konec", 36500.0), stale=stale,
        promenne=prom, nastaveni=nast, projekt=d.get("projekt", {}), n_rezu=n.get("pocet_rezu", 41),
        charakteristiky=n.get("charakteristiky", "brutto"), pocet_napinani=n.get("pocet_napinani"),
        relaxace_pred_uvolnenim_h=pd.get("relaxace_pred_uvolnenim_h"),
        predem_eta_p1=pd.get("eta_p1", 3.2), predem_alpha1=pd.get("alpha1", 1.25),
        predem_alpha2=pd.get("alpha2", 0.19), predem_eta_p2=pd.get("eta_p2", 1.2), kombinace_vstup=komb,
        kombinace_vcetne_g0=bool(zat.get("obsahuje_vlastni_tihu", False)), t_vneseni=zat.get("t_vneseni"),
        t_akt=co.get("t_akt"), oslabeni_Ap=deg.get("oslabeni_predpinaci", 0.0),
        oslabeni_As=deg.get("oslabeni_betonarske", 0.0), oslabeni_Asw=deg.get("oslabeni_smykove", 0.0),
        teplota=Teplota.ze_slovniku(d.get("teplota")),
        kontaktni_spara=bool(n.get("kontaktni_spara", False)), pozice_spar=n.get("pozice_spar"),
    )


def nacti_model(cesta: str | Path) -> NosnikPB:
    return model_ze_slovniku(nacti_soubor(cesta))
