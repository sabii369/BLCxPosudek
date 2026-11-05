"""
Spojený program BLC × Posudek PB: vstupy z posudku (L0, beton, průřez, γ), výběr
vozidla, zatížení nosníku z obálek, posudek, dávkový výpočet a GUI.
"""
import copy
import os
import time
import tkinter as tk
import tomllib

import pytest
from pytest import approx

from blc.beam_1d import Nosnik1D
from blc.geometry import Konstrukce
from blc_posudek.vypocet import (nacti, parametry_blc, spocti, vlastnosti_prurezu, vyber_nosnik,
                                 zatizeni_z_blc)

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIKLAD = os.path.join(KOREN, "priklady", "most_KA67_12.toml")


@pytest.fixture(scope="module")
def d():
    return nacti(PRIKLAD)


@pytest.fixture(scope="module")
def vysledek(d):
    return spocti(copy.deepcopy(d))


def test_parametry_z_posudku(d):
    kw = parametry_blc(d)
    A, Iy = vlastnosti_prurezu(d)
    assert A == approx(0.3116, rel=2e-3)              # KA-67 (Excel: 311 600 mm²)
    assert kw["A_nosniku"] == A and kw["Iy"] == Iy
    assert kw["L"] == d["nosnik"]["L0"] == 11.4
    assert kw["beton"] == d["beton"]["trida"]
    assert kw["Ve"] == 80.0 and "MLC" not in kw
    assert kw["soucinitele"].gamma_G == 1.35          # z [posouzeni] (výchozí)
    assert kw["k_pod"] == 2.0e6


def test_vyber_vozidla(d):
    d2 = copy.deepcopy(d)
    d2["blc"].update(vozidlo="MLC_p", MLC="MLC60")
    kw = parametry_blc(d2)
    assert kw["MLC"] == "MLC60" and kw["typ_MLC"] == "p" and "Ve" not in kw
    d2["blc"]["vozidlo"] = "xyz"
    with pytest.raises(ValueError):
        parametry_blc(d2)


def test_jedno_vozidlo_MLC():
    K = Konstrukce(L=[20.0], N=1, b=1.0, E=34000.0, Iy=0.05)
    nos = Nosnik1D(K)
    ax, _ = next(nos.stavy_MLC("k", "MLC80", 10, None, 0.0))
    assert len(ax) == 5                                # jedno kolové vozidlo = 5 náprav
    ax, _ = next(nos.stavy_MLC("k", "MLC80", 10, 30.5, 0.0))
    assert len(ax) > 5                                 # kolona


def test_spocti_posudek(d, vysledek):
    vys, o, model = vysledek
    assert vys.popisky[o] == "N6"
    assert model.protokol.posudky
    assert [k.nazev for k in model.protokol.kapitoly].index("Zatížení z modelu mostu (BLC)") < \
        [k.nazev for k in model.protokol.kapitoly].index("Zatížení a časová osa")
    zat = zatizeni_z_blc(vys, d, o)
    assert [k["druh"] for k in zat["kombinace"]] == ["6.10a", "6.10b", "char", "casta", "kvazistala"]
    assert zat["kombinace"][0]["x"][-1] == approx(d["nosnik"]["L"])
    assert zat["t_vneseni"] == 60
    assert model.kombinace_vcetne_g0 is False


def test_zadany_nosnik_a_rezim(d, vysledek):
    vys = vysledek[0]
    d2 = copy.deepcopy(d)
    d2["blc"].update(vystup="N2", rezim="zatezovaci_stavy")
    assert vyber_nosnik(vys, d2) == 1
    zat = zatizeni_z_blc(vys, d2)
    assert zat["zpusob"] == "zatezovaci_stavy"
    assert zat["stale"][0]["t"] == 60                  # g − g0 od t_vneseni
    assert "Ve 80 t" in zat["promenne"][0]["nazev"]


def test_davka(tmp_path):
    from blc_posudek.__main__ import main
    rc = main([PRIKLAD, "-o", str(tmp_path)])
    assert rc in (0, 1)
    assert (tmp_path / "protokol.html").exists()
    assert (tmp_path / "most" / "vnitrni_sily.json").exists()
    html = (tmp_path / "protokol.html").read_text(encoding="utf-8")
    assert "Zatížení z modelu mostu (BLC)" in html


def _tk() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


@pytest.mark.skipif(not _tk(), reason="není k dispozici grafické prostředí")
def test_gui(tmp_path):
    from blc_posudek.gui import AplikaceMost
    app = AplikaceMost(PRIKLAD)
    try:
        app.update()
        texty = [app.nb.tab(t, "text") for t in app.nb.tabs()]
        assert texty[0].startswith("0  Most") and len(texty) == 8
        # L0 na kartě 0 je táž proměnná jako na kartě 3
        app.f_nosnik.prom["L0"].set("11.4")
        app.spocitej()
        t0 = time.time()
        while (app.model is None or app._zaneprazdnen) and time.time() - t0 < 300:
            app.update()
            time.sleep(0.05)
        assert app.model is not None
        assert len(app.t_blc.get_children()) == 10
        d = app.ziskej_data()
        assert d["zatizeni"]["zpusob"] == "kombinace" and len(d["zatizeni"]["kombinace"]) == 5
        app.f_voz.prom["vozidlo"].set("MLC kolové")
        assert app._aktualni_blc(app.ziskej_data()) is None      # vstupy se změnily
        app.soubor = tmp_path / "most.toml"
        app.uloz()
        ulozeno = tomllib.loads((tmp_path / "most.toml").read_text(encoding="utf-8"))
        assert ulozeno["blc"]["vozidlo"] == "MLC_k"
    finally:
        app.destroy()
