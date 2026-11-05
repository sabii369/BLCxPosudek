"""
Vnitřní síly pro posudek (g0, g − g0, q) a export do Posudku PB:
analytika prostého nosníku, rovnováha stálého zatížení, vybavení, pohyblivé
zatížení proti 1D modelu, export TOML.
"""
import json
import os
import tomllib

import numpy as np
import pytest
from pytest import approx

from blc.beam_1d import Nosnik1D, vypocet_Ve
from blc.export_pb import (toml_zatizeni_pb, uloz_vysledky, vloz_do_vstupu_pb,
                           zatizeni_pb_dict)
from blc.geometry import Konstrukce, E_betonu
from blc.stale_zatizeni import Vybaveni, LiniovaZatizeni, platky_plosne
from blc.vnitrni_sily import vnitrni_sily, Soucinitele
from blc.vstup_sily import spocti_ze_souboru

L0 = 11.4
NOSNIKY = dict(L=L0, N=6, b=1.0, Iy=0.014375, beton="C35/45", d=0.55)
VYB = Vybaveni(chodnik_L=1.0, chodnik_P=0.5, g_chodnik=5.0, g_vozovka=2.5,
               g_zabradli=0.5, g_svodidla=0.6)


@pytest.fixture(scope="module")
def vys():
    return vnitrni_sily(**NOSNIKY, vybaveni=VYB, A_nosniku=0.3, Ve=60.0, ex=0.125,
                        krok=0.5, tisk=False)


# ---- vybavení -----------------------------------------------------------------

def test_vybaveni_zony_a_tiha():
    B = 6.0
    z = VYB.zony(B)
    assert [n for n, *_ in z] == ["chodník L", "vozovka", "chodník P"]
    assert VYB.sirka_vozovky(B) == approx(4.5)
    assert VYB.y_osy_vozovky(B) == approx(1.0 + 2.25)
    q = 5.0 * 1.5 + 2.5 * 4.5 + 2 * 0.5 + 2 * 0.6
    assert VYB.tiha_na_metr(B) == approx(q)
    F = sum(p[0] for p in VYB.platky(B, 0.0, 10.0))
    assert F == approx(10.0 * q)


def test_vybaveni_kontrola():
    with pytest.raises(ValueError):
        Vybaveni(chodnik_L=3.0, chodnik_P=3.0).kontrola(6.0)
    with pytest.raises(ValueError):
        Vybaveni(liniova=[LiniovaZatizeni("x", 1.0, 7.0)]).kontrola(6.0)


def test_platky_plosne_sila():
    p = platky_plosne(3.0, 0.0, 7.0, 0.0, 1.3)
    assert sum(t[0] for t in p) == approx(3.0 * 7.0 * 1.3)
    assert max(t[2] - t[1] for t in p) <= 2.0 + 1e-12


# ---- g0 -------------------------------------------------------------------------

def test_g0_samostatny_nosnik_analyticky(vys):
    g0 = 0.3 * 25.0
    assert vys.g0 == approx(g0)
    for o in range(vys.n_vyst):
        t = vys.tabulka(o, "g0")
        assert t.M_max.max() == approx(g0 * L0 ** 2 / 8, rel=2e-3)
        assert t.V_max[0] == approx(g0 * L0 / 2, rel=1e-6)
        assert t.V_max[-1] == approx(-g0 * L0 / 2, rel=1e-6)
        assert t.x[0] == 0.0 and t.x[-1] == approx(L0)


def test_g0_spojity_nosnik_dve_pole():
    v = vnitrni_sily(L=[10.0, 10.0], N=3, b=1.0, Iy=0.0144, beton="C30/37", g0=10.0,
                     tisk=False)
    t = v.tabulka(1, "g0")
    # spojitý nosník 2 × L, rovnoměrné q: M nad podporou −qL²/8, reakce krajní 3/8 qL
    assert t.M_min.min() == approx(-10.0 * 100 / 8, rel=5e-3)
    assert t.V_max[0] == approx(3 / 8 * 10 * 10, rel=5e-3)
    # nad vnitřní podporou dva řádky se stejným x
    i = np.where(np.isclose(t.x, 10.0))[0]
    assert len(i) == 2
    assert t.V_max[i[0]] == approx(-5 / 8 * 100, rel=5e-3)
    assert t.V_max[i[1]] == approx(5 / 8 * 100, rel=5e-3)


def test_g0_deska_mkp():
    v = vnitrni_sily(L=10.0, b=6.0, h=0.5, beton="C30/37", typ_konstrukce="deska",
                     tisk=False)
    assert v.g0 == approx(0.5 * 25.0)
    o = v.n_vyst // 2
    t = v.tabulka(o, "g0")
    # kolmá deska, rovnoměrné zatížení: střední pás ≈ válcový ohyb q·L²/8 na 1 m
    assert t.M_max.max() == approx(12.5 * 100 / 8, rel=0.03)


# ---- g − g0 ---------------------------------------------------------------------

def test_g_rovnovaha(vys):
    k = vys.kontrola
    assert k["g_F"] == approx(VYB.tiha_na_metr(6.0) * L0, rel=1e-6)
    assert k["g_R"] == approx(k["g_F"], rel=1e-6)
    # Σ momentů v polovině rozpětí přes nosníky = statika celé konstrukce
    q = VYB.tiha_na_metr(6.0)
    sM = sum(np.interp(L0 / 2, vys.tabulka(o, "g-g0").x, vys.tabulka(o, "g-g0").M_max)
             for o in range(vys.n_vyst))
    assert sM == approx(q * L0 ** 2 / 8, rel=5e-3)


def test_g_spary_samostatne():
    v = vnitrni_sily(L=L0, N=4, b=1.15, Iy=0.07, spara=True, b_s=0.35, Iy_s=0.016,
                     beton="C45/55", g0=10.0, g_spary=4.0, tisk=False)
    Mmax = [v.tabulka(o, "g-g0").M_max.max() for o in range(4)]
    # krajní nosník nese ½ spáry, vnitřní celou (½ + ½)
    assert Mmax[0] == approx(2.0 * L0 ** 2 / 8, rel=3e-3)
    assert Mmax[1] == approx(4.0 * L0 ** 2 / 8, rel=3e-3)


# ---- q ----------------------------------------------------------------------------

def test_q_obalka_proti_1D(vys):
    K = Konstrukce(L=[L0], N=6, b=1.0, E=E_betonu("C35/45"), Iy=0.014375, d=0.55)
    r1 = vypocet_Ve(Nosnik1D(K), 60.0, 40, K.h_ekv)
    M1 = r1.M_max.max()
    Mn = [vys.tabulka(o, "q").M_max.max() for o in range(vys.n_vyst)]
    # nejzatíženější nosník nese část, součet obálek ≥ celý most
    assert max(Mn) < M1
    assert sum(Mn) >= 0.99 * M1
    assert "q" in vys.stavy and vys.stavy["q"].pohyblivy


def test_q_dynamicky_soucinitel():
    a = vnitrni_sily(**NOSNIKY, Ve=60.0, krok=0.5, tisk=False)
    b = vnitrni_sily(**NOSNIKY, Ve=60.0, krok=0.5, dyn=1.2, tisk=False)
    assert b.tabulka(2, "q").M_max.max() == approx(1.2 * a.tabulka(2, "q").M_max.max())


def test_q_poloha_vozidla_osa_vozovky(vys):
    assert vys.y_Ve == approx(VYB.y_osy_vozovky(6.0))
    v = vnitrni_sily(**NOSNIKY, Ve=60.0, krok=0.5, y_Ve=1.5, tisk=False)
    Mn = [v.tabulka(o, "q").M_max.max() for o in range(v.n_vyst)]
    assert int(np.argmax(Mn)) in (0, 1)


# ---- kombinace a výběr nosníku ---------------------------------------------------

def test_kombinace(vys):
    s = vys.soucinitele
    o = 2
    g, q = vys.tabulka(o, "g-g0"), vys.tabulka(o, "q")
    k = vys.kombinace(o, "6.10b")
    assert k.M_max == approx(s.xi * s.gamma_G * g.M_max + s.gamma_Q * q.M_max)
    k = vys.kombinace(o, "kvazistala")
    assert k.M_max == approx(g.M_max + s.psi2 * q.M_max)
    k = vys.kombinace(o, "6.10", vcetne_g0=True)
    g0 = vys.tabulka(o, "g0")
    assert k.M_max == approx(s.gamma_G * (g0.M_max + g.M_max) + s.gamma_Q * q.M_max)


def test_rozhodujici(vys):
    sh = vys.souhrn()
    o = vys.rozhodujici("M")
    assert sh[o]["M_Ed"] == max(d["M_Ed"] for d in sh)
    assert 0 <= vys.rozhodujici("V") < vys.n_vyst


# ---- export do posudku PB --------------------------------------------------------

def test_export_kombinace(vys):
    d = tomllib.loads(toml_zatizeni_pb(vys, 2, L_nosniku=11.96))["zatizeni"]
    assert d["zpusob"] == "kombinace" and d["obsahuje_vlastni_tihu"] is False
    druhy = [k["druh"] for k in d["kombinace"]]
    assert druhy == ["6.10a", "6.10b", "char", "casta", "kvazistala"]
    k = d["kombinace"][1]
    x = np.array(k["x"])
    assert x[0] == 0.0 and x[-1] == approx(11.96)
    assert x[1] == approx(0.28)                      # osa ložiska (L − L0)/2
    assert np.all(np.diff(x) > 0)
    for c in ("M_max", "M_min", "V_max", "V_min"):
        assert len(k[c]) == len(x)
    ref = vys.kombinace(2, "6.10b")
    assert max(k["M_max"]) == approx(ref.M_max.max(), abs=0.01)


def test_export_zatezovaci_stavy(vys):
    d = zatizeni_pb_dict(vys, 0, rezim="zatezovaci_stavy", msu="6.10", t_stale=60)
    assert d["zpusob"] == "zatezovaci_stavy"
    st, pr = d["stale"][0], d["promenne"][0]
    assert st["t"] == 60 and st["gamma"] == 1.35
    assert len(st["tabulka"]["x"]) == len(st["tabulka"]["M"]) == len(st["tabulka"]["V"])
    assert max(pr["tabulka"]["M"]) == approx(vys.tabulka(0, "q").M_max.max(), abs=0.01)


def test_vloz_do_vstupu_pb():
    pb = ('[nosnik]\nL = 11.96\nL0 = 11.4\n\n[zatizeni]\nzpusob = "kombinace"\n\n'
          '[[zatizeni.kombinace]]\ndruh = "char"\nq = 5.0\n\n[posouzeni]\nk1 = 0.6\n')
    frag = '[zatizeni]\nzpusob = "zatezovaci_stavy"\n'
    d = tomllib.loads(vloz_do_vstupu_pb(pb, frag))
    assert d["zatizeni"] == {"zpusob": "zatezovaci_stavy"}
    assert d["posouzeni"]["k1"] == 0.6 and d["nosnik"]["L0"] == 11.4


def test_uloz_vysledky(vys, tmp_path):
    pb = tmp_path / "nosnik.toml"
    pb.write_text('[nosnik]\nL = 11.96\nL0 = 11.4\n\n[zatizeni]\nt_vneseni = 60\n'
                  '[[zatizeni.kombinace]]\ndruh = "char"\nq = 5.0\n', encoding="utf-8")
    soubory = uloz_vysledky(vys, str(tmp_path / "out"), pb_vstup=str(pb))
    jmena = sorted(os.path.basename(s) for s in soubory)
    o = vys.rozhodujici("M")
    assert jmena == sorted(["vnitrni_sily.json", "souhrn.csv", f"{vys.popisky[o]}_stavy.csv",
                            "zatizeni_PB.toml", "nosnik_BLC.toml"])
    j = json.loads((tmp_path / "out" / "vnitrni_sily.json").read_text(encoding="utf-8"))
    assert j["posuzovany_vystup"] == vys.popisky[o]
    assert set(j["vystupy"]) == set(vys.popisky)
    d = tomllib.loads((tmp_path / "out" / "nosnik_BLC.toml").read_text(encoding="utf-8"))
    assert d["zatizeni"]["t_vneseni"] == 60
    assert len(d["zatizeni"]["kombinace"]) == 5


def test_vstup_ze_souboru(tmp_path):
    koren = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vys, soubory = spocti_ze_souboru(os.path.join(koren, "priklady", "sily_KA67_12.toml"),
                                     slozka=str(tmp_path), grafy=True, tisk=False)
    assert vys.K.N == 10 and vys.K.L == [11.4]
    assert vys.g0 == approx(0.3116 * 25)
    assert any(s.endswith("pricne_rozdeleni.png") for s in soubory)
    d = tomllib.loads((tmp_path / "zatizeni_PB.toml").read_text(encoding="utf-8"))
    assert d["zatizeni"]["kombinace"][0]["x"][-1] == approx(11.96)


def test_soucinitele_faktory():
    s = Soucinitele(gamma_G=1.35, xi=0.85, gamma_Q=1.5, psi0=0.4)
    assert s.faktory("6.10a") == (1.35, 1.0, 1.5 * 0.4)
    assert s.faktory("6.10b") == (approx(0.85 * 1.35), 1.0, 1.5)
