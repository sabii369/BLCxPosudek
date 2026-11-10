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
    assert kw["q_chodnik"] == 3.0 and kw["soucinitele"].psi1_ch == 0.75


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
    # mez lineárního dotvarování (7.2(3)) není posudek – v příkladu je překročena → upozornění
    assert not any("dotvarování" in p.nazev for p in model.protokol.posudky)
    upoz = model.protokol.upozorneni
    assert upoz and all("mez lineárního dotvarování" in t for t in upoz)
    assert any(t.startswith("Uvedení do provozu") for t in upoz)


def test_zadany_nosnik_a_rezim(d, vysledek):
    vys = vysledek[0]
    d2 = copy.deepcopy(d)
    d2["blc"].update(vystup="N2", rezim="zatezovaci_stavy")
    assert vyber_nosnik(vys, d2) == 1
    zat = zatizeni_z_blc(vys, d2)
    assert zat["zpusob"] == "zatezovaci_stavy"
    assert zat["stale"][0]["t"] == 60                  # g − g0 od t_vneseni
    assert "chodců" in zat["promenne"][0]["nazev"] and "Ve 80 t" in zat["promenne"][1]["nazev"]


def test_napeti_v_rezech(vysledek):
    import numpy as np
    from blc_posudek.grafy_most import profily_faze, rezy_posudku
    vys, o, model = vysledek
    rz = rezy_posudku(model)
    i, x = rz["podpora"]
    assert 0.0 < x < 1.5 and i != model.ia
    for idx, f in enumerate(model.faze):
        res = model.msp_napeti[f.nazev]
        for ii in (rz["stred"][0], i):
            prof = profily_faze(model, idx, ii)
            assert list(prof) == list(res)                 # stejné kombinace jako graf po délce
            for druh, (z, lo, hi) in prof.items():
                sh = [v[0][ii] for v in res[druh].values()]
                sd = [v[1][ii] for v in res[druh].values()]
                assert lo[0] == approx(min(sd)) and hi[0] == approx(max(sd))    # dolní vlákna
                assert lo[-1] == approx(min(sh)) and hi[-1] == approx(max(sh))  # horní vlákna
                assert np.all(lo <= hi + 1e-12)


def test_grafy_most(vysledek):
    import matplotlib.pyplot as plt
    from pb_posudek import grafy
    from blc_posudek.grafy_most import seznam_grafu
    model = vysledek[2]
    s = seznam_grafu(model)
    assert len(s) == 3 + len(model.faze)
    with grafy.vracet_obrazky():
        for nazev, fn in s.items():
            fig = fn(model, None)
            n_os = 2 * len(vysledek[0].stavy) if nazev.endswith("na nosnících") else 2
            assert fig is not None and len(fig.axes) == n_os, nazev
            plt.close(fig)


def test_obrazky_v_kapitolach(vysledek):
    model = vysledek[2]
    kap = {k.nazev: [o.soubor for t, o in k.polozky if t == "obrazek"] for k in model.protokol.kapitoly}
    assert kap["Zatížení z modelu mostu (BLC)"] == ["blc_zat_stale", "blc_zat_q", "blc_sily"]
    tab = [o for t, o in next(k for k in model.protokol.kapitoly
                              if k.nazev == "Zatížení z modelu mostu (BLC)").polozky if t == "tabulka"]
    assert len(tab) == 2 + 6                               # součinitele, stavy, 6 kombinací
    # součinitele podle zadání: char, častá, kvazi, 6.10a, 6.10b, 6.10 × (G, chodci, doprava)
    assert [r[1:] for r in tab[0].radky] == [
        ["1,00"] * 6, ["1,00", "1,00", "1,00", "0,75", "1,00", "0,75"],
        ["1,00", "1,00", "1,00", "0,00", "1,00", "0,00"],
        ["1,35", "1,00", "1,35", "0,75", "1,35", "0,75"],
        ["1,35", "0,85", "1,35", "1,00", "1,35", "1,00"], ["1,35", "1,00", "1,35", "1,00", "1,35", "1,00"]]
    assert "chodci" in " ".join(tab[1].hlavicka)
    for idx, f in enumerate(model.faze):
        obr = kap[f"Napětí v betonu – {f.nazev_t}"]
        assert obr[obr.index(f"napeti_{idx}") + 1] == f"blc_rez_{idx}"   # hned pod grafem fáze


def test_davka(tmp_path):
    from blc_posudek.__main__ import main
    rc = main([PRIKLAD, "-o", str(tmp_path)])
    assert rc in (0, 1)
    assert (tmp_path / "protokol.html").exists()
    assert (tmp_path / "most" / "vnitrni_sily.json").exists()
    html = (tmp_path / "protokol.html").read_text(encoding="utf-8")
    assert "Zatížení z modelu mostu (BLC)" in html
    for naz in ("charakteristická", "častá", "kvazistálá", "MSÚ 6.10a", "MSÚ 6.10b", "MSÚ 6.10"):
        assert f"Kombinace {naz} – vnitřní síly po nosnících" in html
    assert (tmp_path / "obrazky" / "blc_sily.png").exists()
    assert "<figcaption>Zatížení na mostě – vlastní tíha g0" in html
    assert "<figcaption>Zatížení na mostě – vozidlo v poloze pro max M" in html
    assert html.count("<figcaption>Napětí po výšce průřezu v řezu ve středu rozpětí") == 4
    for k in ("blc_zat_stale", "blc_zat_q", "blc_rez_0", "blc_rez_3"):
        assert (tmp_path / "obrazky" / f"{k}.png").exists()
    assert '<div class="upoz"><b>Upozornění</b>' in html          # souhrn upozornění


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
        assert "mez lineárního dotvarování" in app.lbl_upozorneni.cget("text")   # upozornění v GUI
        assert app.lbl_upozorneni.winfo_manager() == "pack"
        nazvy = list(app._seznam_grafu)
        assert "Zatížení mostu – vlastní tíha g0 a ostatní stálé g − g0" in nazvy
        i = nazvy.index("Napětí v betonu – Konec životnosti")
        assert nazvy[i + 1] == "Napětí v řezech – Konec životnosti"
        app._zobraz_graf("Napětí v řezech – Konec životnosti")
        assert app.var_graf.get() == "Napětí v řezech – Konec životnosti"
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


# ---- zatížitelnost ------------------------------------------------------------

@pytest.fixture(scope="module")
def zat(d, vysledek):
    from blc_posudek.zatizitelnost import zatizitelnost
    return zatizitelnost(copy.deepcopy(d), vysledek[0])


def test_vys_pro_Ve(vysledek):
    from blc_posudek.zatizitelnost import vys_pro_Ve
    vys = vysledek[0]
    v2 = vys_pro_Ve(vys, 2.5 * vys.Ve)
    assert v2.stavy["q"].M_max == approx(2.5 * vys.stavy["q"].M_max)
    assert v2.stavy["g-g0"] is vys.stavy["g-g0"] and vys.Ve == 80.0     # originál beze změny
    assert v2.vozidlo == "Ve 200.0 t"


def test_zatizitelnost(zat):
    from blc_posudek.zatizitelnost import klic_posudku
    m = zat.minimum()
    assert m is not None and m.Ve > zat.Ve_ref                     # příklad vyhovuje při 80 t
    eta = {klic_posudku(p): p.vyuziti for p in zat.model.protokol.posudky}
    assert eta[m.klic] == approx(1.0, abs=2e-3)                    # rozhodující posudek na 100 %
    assert zat.vys.Ve == approx(m.Ve)
    for p in zat.posudky:
        if p.stav == "Ve":                                          # žádný jiný nepřekročen
            assert eta[p.klic] <= 1.0 + 2e-3
    stavy = {p.klic[1]: p.stav for p in zat.posudky}
    assert stavy["Napínací napětí – K7"] == "nezavisi_nok"
    assert stavy["Křehký lom – redukované předpětí"] == "klesa"
    assert zat.minimum("MSÚ").Ve <= zat.minimum("MSP").Ve
    assert zat.model.protokol.kapitoly[0].nazev.startswith("Zatížitelnost")


def test_zatizitelnost_jen_Ve(d):
    from blc_posudek.zatizitelnost import zatizitelnost
    d2 = copy.deepcopy(d)
    d2["blc"]["vozidlo"] = "MLC_k"
    with pytest.raises(ValueError):
        zatizitelnost(d2)


def test_davka_zatizitelnost(tmp_path):
    from blc_posudek.__main__ import main
    assert main([PRIKLAD, "--zatizitelnost", "-o", str(tmp_path)]) == 0
    html = (tmp_path / "protokol.html").read_text(encoding="utf-8")
    assert "Zatížitelnost – tíha vozidla Ve pro dosažení mezních stavů" in html


def test_aktualni_stari_a_koroze(d, vysledek):
    vys = vysledek[0]
    d2 = copy.deepcopy(d)
    d2["casova_osa"]["t_akt"] = 18250.0
    d2["degradace"] = {"oslabeni_predpinaci": 10.0, "oslabeni_betonarske": 10.0, "oslabeni_smykove": 20.0}
    d2.setdefault("predpinaci_vyztuz", {})["taznost_oslabena"] = 10.0
    _, o, m = spocti(d2, vys)
    nazvy = [f.nazev for f in m.faze]
    assert "Aktuální stáří" in nazvy and nazvy[-1] == "Konec životnosti"
    assert m.faze[nazvy.index("Aktuální stáří")].k_Asw == approx(0.8)
    assert [f.eps_ud_p for f in m.faze if f.t < 18250.0] == [None] * (len(nazvy) - 2)
    assert m.faze[nazvy.index("Aktuální stáří")].eps_ud_p == approx(0.009)   # ε_ud,red = 0,9·10 ‰
    eta0 = {(p.nazev, p.faze): p.vyuziti for p in vysledek[2].protokol.posudky}
    eta1 = {(p.nazev, p.faze): p.vyuziti for p in m.protokol.posudky}
    k = ("Smyková únosnost", "Konec životnosti")
    assert eta1[k] > eta0[k]
    assert ("Ohybová únosnost", "Aktuální stáří") in eta1


@pytest.mark.skipif(not _tk(), reason="není k dispozici grafické prostředí")
def test_gui_koroze():
    from blc_posudek.gui import AplikaceMost
    app = AplikaceMost(PRIKLAD)
    try:
        app.update()
        app.f_cas.prom["t_akt"].set("18250")
        app.f_degradace.prom["oslabeni_smykove"].set("15")
        app.f_predp.prom["taznost_oslabena"].set("12")
        d = app.ziskej_data()
        assert d["casova_osa"]["t_akt"] == 18250.0 and d["degradace"] == {"oslabeni_smykove": 15.0}
        assert d["predpinaci_vyztuz"]["taznost_oslabena"] == 12.0
    finally:
        app.destroy()
