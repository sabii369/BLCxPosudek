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
from blc_posudek.vypocet import (nacti, parametry_blc, polohy_modelu, priprav_protokol, spocti,
                                 vlastnosti_prurezu, vyber_nosnik, zatizeni_z_blc)

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIKLAD = os.path.join(KOREN, "priklady", "most_KA67_12.toml")


@pytest.fixture(scope="module")
def d():
    return nacti(PRIKLAD)


@pytest.fixture(scope="module")
def vysledek(d):
    return spocti(copy.deepcopy(d))


def test_beta_s_pevne(d):
    assert parametry_blc(d)["beta_s_pevne"] is False
    d2 = copy.deepcopy(d)
    d2["blc"]["beta_s_pevne"] = True
    kw = parametry_blc(d2)
    assert kw["beta_s_pevne"] is True
    K = Konstrukce(L=[kw["L"]], N=kw["N"], b=kw["b"], E=3.4e7, Iy=kw["Iy"], k_pod=kw["k_pod"],
                   uloz=kw["uloz"], beta_s_pevne=kw["beta_s_pevne"])
    assert not K.beta_s_sleduje and "β_s = 0" in K.popis_ulozeni()


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
    assert kw["q_chodnik"] is None and kw["soucinitele"].psi1_ch == 0.75   # chodci podle normy
    assert kw["dyn"] is None                          # δ podle ČSN 73 6222, kap. 8
    d2 = copy.deepcopy(d)
    d2["blc"]["dyn"] = 1.2
    assert parametry_blc(d2)["dyn"] == 1.2


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
    assert vys.dyn == 1.05 and "čl. 8.4" in vys.dyn_zdroj      # δ podle ČSN 73 6222 (Ve)
    assert model.protokol.posudky
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


def test_protokol_az_pri_ulozeni(d):
    """spocti počítá jen most a posudek; polohy vozidla a kapitoly BLC až priprav_protokol."""
    vys, o, model = spocti(copy.deepcopy(d))
    nazvy = [k.nazev for k in model.protokol.kapitoly]
    assert "Zatížení z modelu mostu (BLC)" not in nazvy and "polohy" not in model.blc
    assert not any(k[0] == "ref_souprava_bez_dyn" for k in vys.cache)
    priprav_protokol(model)
    priprav_protokol(model)                                   # podruhé nic nepřidá
    nazvy = [k.nazev for k in model.protokol.kapitoly]
    assert nazvy.count("Zatížení z modelu mostu (BLC)") == 1
    assert nazvy.index("Zatížení z modelu mostu (BLC)") < nazvy.index("Zatížení a časová osa")
    assert set(model.blc["polohy"]) == {"M", "V"}


def test_zadany_nosnik_a_rezim(d, vysledek):
    vys = vysledek[0]
    d2 = copy.deepcopy(d)
    d2["blc"].update(vystup="N2", rezim="zatezovaci_stavy")
    assert vyber_nosnik(vys, d2) == 1
    zat = zatizeni_z_blc(vys, d2)
    assert zat["zpusob"] == "zatezovaci_stavy"
    assert zat["stale"][0]["t"] == 60                  # g − g0 od t_vneseni
    # Ve: chodci vyloučeni (ČSN 73 6222, čl. 3.1.4) – jen doprava
    assert len(zat["promenne"]) == 1 and "Ve 80 t" in zat["promenne"][0]["nazev"]


@pytest.fixture(scope="module")
def vysledek_teplota(d):
    d2 = copy.deepcopy(d)
    d2["teplota"] = {"svrsek": 0.18}
    return spocti(d2)


@pytest.mark.parametrize("fixt", ["vysledek", "vysledek_teplota"])
def test_napeti_v_rezech(fixt, request):
    import numpy as np
    from blc_posudek.grafy_most import profily_faze, rezy_posudku
    vys, o, model = request.getfixturevalue(fixt)
    if fixt == "vysledek_teplota":   # provozní fáze mají varianty s teplotou (nelineární průběh)
        assert model.vys_teplota is not None
        assert any(len(k) == 3 for k in model.msp_napeti[model.faze[-1].nazev]["char"])
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
    assert len(s) == 4 + len(model.faze)                  # g, q, příčný řez, síly + řezy fází
    with grafy.vracet_obrazky():
        for nazev, fn in s.items():
            fig = fn(model, None)
            n_os = (2 * len(vysledek[0].stavy) if nazev.endswith("na nosnících") else
                    1 if "příčný řez" in nazev else 2)
            assert fig is not None and len(fig.axes) == n_os, nazev
            plt.close(fig)


def test_obrazky_v_kapitolach(vysledek):
    model = vysledek[2]
    priprav_protokol(model)
    kap = {k.nazev: [o.soubor for t, o in k.polozky if t == "obrazek"] for k in model.protokol.kapitoly}
    assert kap["Zatížení z modelu mostu (BLC)"] == ["blc_zat_stale", "blc_zat_q", "blc_zat_pricny",
                                                    "blc_sily"]
    tab = [o for t, o in next(k for k in model.protokol.kapitoly
                              if k.nazev == "Zatížení z modelu mostu (BLC)").polozky if t == "tabulka"]
    assert len(tab) == 2 + 2                               # součinitele, stavy, kombinace M a V
    # součinitele podle zadání: char, častá, kvazi, 6.10a, 6.10b (kombinace_msu = 6.10ab)
    # × (G, doprava); s Ve chodci nejsou (ČSN 73 6222, čl. 3.1.4)
    assert [r[1:] for r in tab[0].radky] == [
        ["1,00"] * 4, ["1,00", "1,00", "1,00", "0,75"], ["1,00", "1,00", "1,00", "0,00"],
        ["1,35", "1,00", "1,35", "0,75"], ["1,35", "0,85", "1,35", "1,00"]]
    # kombinace po nosnících: sloupce = kombinace, řádky = nosníky
    assert tab[2].hlavicka == ["Nosník", "charakteristická", "častá", "kvazistálá", "MSÚ 6.10a",
                               "MSÚ 6.10b"] and len(tab[2].radky) == 10
    assert tab[2].radky[5][0] == "N6 ◄" and tab[3].popisek.startswith("Kombinace po nosnících – max |V|")
    from pb_posudek.protokol import fmt
    m_ed = vysledek[0].extremy_kombinace("6.10b")[5]["M_max"]
    assert tab[2].radky[5][-1] == fmt(m_ed)
    assert "chodci" not in " ".join(tab[1].hlavicka)
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
    assert "δ = 1,05 (ČSN 73 6222, čl. 8.4, výjimečná zatížitelnost)" in html     # desetinná čárka
    assert "x posudku = x od osy podpory + (L − L0)/2" in html
    assert "Kombinace po nosnících – max M [kNm]" in html and "Kombinace po nosnících – max |V| [kN]" in html
    hlav = html[html.index("<h1>"):html.index('<h2 id="souhrn">')]           # hlavička protokolu
    assert "<dt>Most</dt><dd>10 nosníků, 1 pole: 11,4 m" in hlav
    assert "<dt>Posuzovaný nosník</dt><dd>N6 (y = 5,50 m) – nejzatíženější podle M_Ed" in hlav
    assert "Ve 80 t" in hlav and "Celkový výsledek:" in hlav
    # tabulka maxim po nosnících: místo zadané dopravy referenční soupravy Vn, Vr, Ve
    for n in ("Vn 32 t", "Vr 60 t", "Ve 80 t"):
        assert f"max M {n} [kNm]" in html and f"max |V| {n} [kN]" in html
    assert "max M doprava" not in html
    assert (tmp_path / "obrazky" / "blc_sily.png").exists()
    assert "<figcaption>Zatížení na mostě – vlastní tíha g0" in html
    assert "<figcaption>Zatížení na mostě – vozidlo v poloze pro max M" in html
    assert html.count("<figcaption>Napětí po výšce průřezu v řezu ve středu rozpětí") == 4
    for k in ("blc_zat_stale", "blc_zat_q", "blc_rez_0", "blc_rez_3"):
        assert (tmp_path / "obrazky" / f"{k}.png").exists()
    assert '<div class="upoz"><b>Upozornění</b>' in html          # souhrn upozornění
    # vysledky.json: předpínací síla jako v protokolu posudku (s oslabením korozí k_Ap)
    import json
    vj = json.loads((tmp_path / "vysledky.json").read_text(encoding="utf-8"))
    assert all(len(f["P_kN"]) == len(vj["x"]) for f in vj["faze"])


def test_soucinitele_bez_prepoctu_mkp(vysledek):
    from blc_posudek.vypocet import klic_mkp, vys_se_soucinitely
    from blc.vnitrni_sily import Soucinitele
    vys = vysledek[0]
    s2 = Soucinitele(gamma_G=1.35, gamma_Q=1.5)
    v2 = vys_se_soucinitely(vys, s2)
    assert v2 is not vys and v2.model is vys.model and v2.stavy is vys.stavy
    assert vys_se_soucinitely(vys, vys.soucinitele) is vys
    assert vys.soucinitele.gamma_Q == 1.35                          # původní beze změny
    i = vysledek[1]
    assert v2.souhrn()[i]["M_Ed"] > vys.souhrn()[i]["M_Ed"]
    kw = {"L": 11.4, "N": 10, "soucinitele": vys.soucinitele}
    assert klic_mkp(kw) == klic_mkp({**kw, "soucinitele": s2})
    assert klic_mkp(kw) != klic_mkp({**kw, "N": 12})


def test_nahled_mostu_bez_mkp(d, vysledek):
    """Náhled příčného řezu ze zadání (bez MKP) = stejná příčná poloha jako výpočet (Ve, Vn, Vr)."""
    from blc.vnitrni_sily import nahled_mostu, vys_s_vozidlem
    atr = ("druh_q", "V", "schema_q", "vozidlo", "y_Ve", "poloha_q", "stopy_q", "pruhy_q", "obrys_q",
           "dyn", "q_ch", "q_ch_zdroj")
    vys = vysledek[0]
    for voz, V in (("Ve", 80.0), ("Vn", 32.0), ("Vr", 60.0)):
        d2 = copy.deepcopy(d)
        d2["blc"]["vozidlo"] = voz
        n = nahled_mostu(**parametry_blc(d2))
        v = vys if voz == "Ve" else vys_s_vozidlem(vys, **{voz: V})
        for a in atr:
            assert getattr(n, a) == getattr(v, a), (voz, a)
        assert n.popisky == v.popisky and list(n.vyst.y) == list(v.vyst.y)


def test_nezname_klice_blc(d):
    d2 = copy.deepcopy(d)
    d2["blc"]["gama_Q"] = 1.5
    with pytest.raises(ValueError, match="gama_Q.*gamma_Q"):
        parametry_blc(d2)
    d2 = copy.deepcopy(d)
    d2["blc"]["liniova"] = [{"nazev": "římsa", "g": 3.0, "y": 0.3, "sirak": 0.4}]
    with pytest.raises(ValueError, match="sirak.*sirka"):
        parametry_blc(d2)


def test_vysledky_json_oslabeni(d, tmp_path):
    """Předpínací síla ve vysledky.json zahrnuje oslabení korozí (Faze.k_Ap)."""
    import json
    from blc_posudek.vypocet import uloz_protokol_most
    d2 = copy.deepcopy(d)
    d2["degradace"] = {"oslabeni_predpinaci": 20.0}      # [%]
    vys, o, m = spocti(d2)
    uloz_protokol_most(m, tmp_path)
    vj = json.loads((tmp_path / "vysledky.json").read_text(encoding="utf-8"))
    f = m.faze[-1]
    assert f.k_Ap == approx(0.8)
    P = -m._sily_predpeti(f.sigma, f.k_Ap)[0]
    assert vj["faze"][-1]["P_kN"] == approx(P.tolist())


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
        assert "dyn" not in d["blc"] and "δ = 1,05 (ČSN 73 6222" in app.lbl_zat.cget("text")
        # jiné součinitele γ, ψ: stejný model MKP, jen se přeskládají kombinace
        vys0 = app._blc_vys
        app.f_souc_doprava.prom["gamma_Q"].set("1.5")
        v2 = app._aktualni_blc(app.ziskej_data())
        assert v2 is not None and v2.model is vys0.model and v2.soucinitele.gamma_Q == 1.5
        i6 = v2.popisky.index("N6")
        assert v2.souhrn()[i6]["M_Ed"] > vys0.souhrn()[i6]["M_Ed"]
        app.f_souc_doprava.prom["gamma_Q"].set("1.35")
        app.f_voz.prom["dyn"].set("1.2")
        assert app.ziskej_data()["blc"]["dyn"] == 1.2
        app.f_voz.prom["vozidlo"].set("MLC kolové")
        assert app._aktualni_blc(app.ziskej_data()) is None      # vstupy se změnily
        app.soubor = tmp_path / "most.toml"
        app.uloz()
        ulozeno = tomllib.loads((tmp_path / "most.toml").read_text(encoding="utf-8"))
        assert ulozeno["blc"]["vozidlo"] == "MLC_k"
        app.var_zat_prot.set("jen Vr – posudky při Vr")
        assert app.ziskej_data()["blc"]["protokol_zatizitelnosti"] == "Vr"
        # režim v liště: zatížitelnost → tlačítko, volby a referenční tíhy všech druhů
        app.var_rezim.set("Zatížitelnost")
        app._zmena_rezimu()
        assert app.ziskej_data()["blc"]["zatizitelnost"] is True
        assert app.btn_vypocet.cget("text").strip().startswith("▶  Zatížitelnost".strip())
        assert app.fr_zat.winfo_manager() == "pack"
        for k in ("Vn", "Vr", "Ve"):
            assert app.f_voz.widgety[k].winfo_manager() == "grid"
        app.var_rezim.set("Posouzení")
        app._zmena_rezimu()
        assert app.ziskej_data()["blc"]["zatizitelnost"] is False and not app.fr_zat.winfo_manager()
    finally:
        app.destroy()


def test_gui_karta0_viditelnost_a_nahled():
    """Karta 0: jen platná pole (deska, spára, převzetí průřezu, vozidlo), náhled řezu bez výpočtu,
    posuzovaný nosník označen."""
    from blc_posudek.gui import AplikaceMost, ZNACKA_POS
    app = AplikaceMost(PRIKLAD)
    try:
        app.update()
        app._viditelnost()
        vid = lambda fm, k: fm.widgety[k].winfo_manager() == "grid"     # noqa: E731
        assert vid(app.f_kon, "N") and not vid(app.f_kon, "h") and not vid(app.f_kon, "Iy")
        assert not vid(app.f_spara, "b_s") and not vid(app.f_uloz, "k_rot")
        assert vid(app.f_voz, "Ve") and not vid(app.f_voz, "Vn") and not vid(app.f_voz, "MLC")
        app.f_kon.prom["prurez_z_posudku"].set(False)
        assert vid(app.f_kon, "Iy") and vid(app.f_kon, "A_nosniku")
        app.f_kon.prom["prurez_z_posudku"].set(True)
        app.f_spara.prom["spara"].set(True)
        assert vid(app.f_spara, "b_s") and not vid(app.f_uloz, "spoj")
        app.f_spara.prom["spara"].set(False)
        app.f_kon.prom["typ_konstrukce"].set("deska")
        assert vid(app.f_kon, "h") and not vid(app.f_kon, "N") and not app.lf_spara.winfo_manager()
        app.f_kon.prom["typ_konstrukce"].set("nosniky")
        assert app.lf_spara.winfo_manager() == "pack"
        app.f_voz.prom["vozidlo"].set("MLC kolové")
        assert vid(app.f_voz, "MLC") and vid(app.f_voz, "dist") and not vid(app.f_voz, "Ve")
        app.f_voz.prom["vozidlo"].set("Vn – normální")
        assert vid(app.f_voz, "Vn") and not vid(app.f_voz, "y_vozidla")
        # náhled příčného řezu ze zadání (bez výpočtu mostu)
        app._nahled()
        assert app._blc_vys is None and app._nahled_zobrazen
        nadpis = app.g_blc.fig.axes[0].get_title()
        assert nadpis.startswith("Náhled ze zadání") and "Vn 32 t" in nadpis
        # po výpočtu mostu: spočtený graf, posuzovaný nosník označen
        app.spocitej_blc()
        t0 = time.time()
        while (app._blc_vys is None or app._zaneprazdnen) and time.time() - t0 < 120:
            app.update()
            time.sleep(0.05)
        assert not app._nahled_zobrazen
        o = vyber_nosnik(app._blc_vys, app.ziskej_data())
        assert app.t_blc.set(str(o), "vyst").endswith(ZNACKA_POS) and "pos" in app.t_blc.item(str(o), "tags")
    finally:
        app.destroy()


# ---- posouzení pro vozidla normální a výhradní zatížitelnosti --------------------

def test_posouzeni_Vn_Vr(d, vysledek):
    from blc.vnitrni_sily import vnitrni_sily, vys_s_vozidlem
    d2 = copy.deepcopy(d)
    d2["blc"]["vozidlo"] = "Vn"
    kw = parametry_blc(d2)
    assert kw["Vn"] == 32.0 and "Ve" not in kw and kw["q_chodnik"] is None
    vys = vys_s_vozidlem(vysledek[0], Vn=32.0)                     # stejný model MKP
    prima = vnitrni_sily(**kw)
    for s in ("q", "qch"):
        assert vys.stavy[s].M_max == approx(prima.stavy[s].M_max)
        assert vys.stavy[s].Vs_min == approx(prima.stavy[s].Vs_min)
    assert vys.q_ch == 2.5 and "tab. 7.1" in vys.q_ch_zdroj       # chodci podle normy
    assert "u pravého kraje vozovky (užší chodník P)" in vys.stavy["q"].popis
    assert [(p["y0"], p["y1"]) for p in vys.pruhy_q] == [(6.25, 9.25), (3.25, 6.25), (1.5, 3.25)]
    assert [p["nazev"] for p in vys.pruhy_q] == ["pruh 1", "pruh 2", "zbývající plocha"]
    _, o, m = spocti(d2, vys)
    pol = polohy_modelu(m)
    assert pol["M"].plosne and len(pol["M"].platky) == 8           # 2 dvounápravy × 4 kola
    priprav_protokol(m)
    kap = next(k for k in m.protokol.kapitoly if k.nazev == "Zatížení z modelu mostu (BLC)")
    tab = [x for t, x in kap.polozky if t == "tabulka"]
    assert "chodci" in " ".join(tab[1].hlavicka)
    d2["blc"]["vozidlo"] = "Vr"
    vr = vys_s_vozidlem(vysledek[0], **{k: v for k, v in parametry_blc(d2).items() if k == "Vr"})
    assert vr.schema_q == "6" and vr.q_ch == 2.5 and vr.y_Ve == approx(9.25 - 1.5)


# ---- zatížitelnost ------------------------------------------------------------

@pytest.fixture(scope="module")
def zat(d, vysledek):
    """Zatížitelnost Vn, Vr, Ve; protokol pro Vn (zvolené vozidlo)."""
    from blc_posudek.zatizitelnost import zatizitelnost
    d2 = copy.deepcopy(d)
    d2["blc"]["vozidlo"] = "Vn"
    return zatizitelnost(d2, vysledek[0])


def test_vys_pro_Ve(vysledek):
    from blc_posudek.zatizitelnost import vys_pro_Ve
    vys = vysledek[0]
    v2 = vys_pro_Ve(vys, 2.5 * vys.Ve)
    assert v2.stavy["q"].M_max == approx(2.5 * vys.stavy["q"].M_max)
    assert v2.stavy["g-g0"] is vys.stavy["g-g0"] and vys.Ve == 80.0     # originál beze změny
    assert v2.vozidlo == "Ve 200,0 t"


def test_zatizitelnost(zat):
    from blc_posudek.zatizitelnost import klic_posudku
    assert zat.druh == "Vn" and list(zat.druhy) == ["Vn", "Vr", "Ve"]
    m = zat.minimum()
    assert m is not None and m.V > zat.hlavni.V_ref                # příklad vyhovuje při 32 t
    eta = {klic_posudku(p): p.vyuziti for p in zat.model.protokol.posudky}
    assert eta[m.klic] == approx(1.0, abs=2e-3)                    # rozhodující posudek na 100 %
    assert zat.vys.druh_q == "Vn" and zat.vys.V == approx(m.V)
    for p in zat.posudky:
        if p.stav == "V":                                           # žádný jiný nepřekročen
            assert eta[p.klic] <= 1.0 + 2e-3
    for z in zat.druhy.values():
        stavy = {p.klic[1]: p.stav for p in z.posudky}
        assert stavy["Napínací napětí – K7"] == "nezavisi_nok"
        assert stavy["Křehký lom – redukované předpětí"] == "klesa"
        assert z.V_evidence == int(z.V)
    # Vn ≥ 16 t → jen dvounáprava; Vr > 50 t → jen šestinápravové vozidlo
    assert list(zat.druhy["Vn"].schemata) == ["dvojnaprava"] and zat.Vn >= 16.0
    assert list(zat.druhy["Vr"].schemata) == ["6"] and zat.Vr > 50.0
    assert zat.Vn < zat.Vr                                          # pruhy + chodci vs. 1 vozidlo
    assert zat.Vaj == approx(max(3 / 8 * zat.Vn, zat.Vr / 6))
    assert zat.druhy["Ve"].prvni.vys.q_ch == 0.0                    # Ve: chodci vyloučeni
    # nosník každého posudku = nosník s nejnižší zatížitelností; rozhodující nosník druhu = nosník minima
    for dr, z in zat.druhy.items():
        assert z.o == z.minimum().o and z.o in z.nosniky, dr
        assert all(p.o in z.nosniky for p in z.posudky), dr
        assert z.n_nosniku == 10 and z.vyber.startswith("nejnižší zatížitelnost přes "), dr
        for p in z.posudky:                       # žádný počítaný nosník nemá nižší V
            if p.stav == "V":
                assert all(q.V >= p.V - 1e-9 for ps in z.nosniky.values() for q in ps
                           if q.klic == p.klic and q.stav == "V"), dr
    assert zat.druhy["Vn"].prvni.vys.q_ch == 2.5
    priprav_protokol(zat.model)
    kap = zat.model.protokol.kapitoly[0]
    assert kap.nazev == "Zatížitelnost podle ČSN 73 6222"
    assert not [o for typ, o in kap.polozky if typ == "obrazek"]     # schémata jsou v kap. 2.4
    blc = next(k for k in zat.model.protokol.kapitoly if k.nazev == "Zatížení z modelu mostu (BLC)")
    obr = [o.soubor for typ, o in blc.polozky if typ == "obrazek"]
    assert obr == (["blc_zat_stale", "blc_zat_q", "blc_zat_pricny"] +
                   [f"blc_{t}_{dr}" for dr in ("Vn", "Vr", "Ve") for t in ("zat", "pricny")] +
                   ["blc_sily"])


def test_grafy_zatizitelnosti(zat):
    import matplotlib.pyplot as plt
    from pb_posudek import grafy
    from blc_posudek.grafy_most import seznam_grafu
    s = seznam_grafu(zat.model)
    with grafy.vracet_obrazky():
        assert "Zatížitelnost – obálky od referenčních souprav" not in s
        fig = s["Zatížení mostu – vnitřní síly na nosnících"](zat.model, None)
        tit = [a.get_title() for a in fig.axes[::2]]      # g0, g − g0, chodci, Vn, Vr, Ve (bez q)
        assert len(tit) == 6 and tit[4].startswith("Vr = 60 t (šestinápravové")
        assert tit[2].startswith("zatížení chodců q_ch = 2,5 kN/m² (s Vn, Vr; s Ve chodci nejsou)")
        assert "bez δ" in tit[4]
        from blc_posudek.grafy_most import q_bez_dyn
        for dr in ("Vn", "Vr", "Ve"):                    # δ1 = 1,25 (Vn: 1 nebo 2 pruhy), Ve 1,05
            v = zat.druhy[dr].vys_ref()
            q0 = q_bez_dyn(v)
            if dr == "Vn":
                assert (q0.M_max <= v.stavy["q"].M_max / 1.2 + 1e-9).all()
            else:
                assert q0.M_max == approx(v.stavy["q"].M_max / v.dyn)
        assert not any(t.startswith("zatížení dopravou q") for t in tit)
        plt.close(fig)
        plt.close(fig)
        for dr in ("Vn", "Vr", "Ve"):
            fig = s[f"Zatížitelnost {dr} – zatížení na mostě (referenční)"](zat.model, None)
            assert len(fig.axes) == 2                         # max M | max V
            plt.close(fig)
            fig = s[f"Zatížitelnost {dr} – příčný řez (referenční)"](zat.model, None)
            assert len(fig.axes) == 1 and dr in fig.axes[0].get_title()
            plt.close(fig)
    z = zat.druhy["Vr"]
    assert z.vys_V().V == approx(z.V) and z.vys_ref().V == 60.0 and z.vys_ref().schema_q == "6"
    p = z.polohy_ref()
    assert sum(pl[0] for pl in p["M"].platky) == approx(10.0 * 60.0 * z.vys_ref().dyn)


def test_protokol_jednoho_druhu(zat):
    from blc_posudek.zatizitelnost import klic_posudku, protokol_druhu
    assert protokol_druhu(zat, "souhrn") is zat.model
    m = protokol_druhu(zat, "Vr")
    assert protokol_druhu(zat, "Vr") is m                          # spočteno jednou
    pohled = m.zatizitelnost
    assert pohled.jen_druh and pohled.celek is zat and list(pohled.druhy) == ["Vr"]
    assert m.blc["vys"].druh_q == "Vr" and m.blc["vys"].V == approx(zat.Vr)
    eta = {klic_posudku(p): p.vyuziti for p in m.protokol.posudky}
    assert eta[zat.druhy["Vr"].minimum().klic] == approx(1.0, abs=2e-3)   # posudky při Vr
    priprav_protokol(m)
    kap = m.protokol.kapitoly[0]
    assert kap.nazev == "Zatížitelnost Vr – výhradní (ČSN 73 6222)"
    tab = [o.popisek for typ, o in kap.polozky if typ == "tabulka"]
    assert any("Zatížitelnost Vr po" in x for x in tab) and not any("Vn po" in x for x in tab)
    assert pohled.Vaj is None                                      # jen s Vn i Vr
    assert protokol_druhu(pohled, "Vn").zatizitelnost.druh == "Vn"   # z pohledu přes celek


def test_slouceni_schemat():
    """Výsledná Vn, Vr po posudcích z výsledků schémat (čl. 7.1.6, 7.2.2)."""
    from blc_posudek.zatizitelnost import PosudekZat, VysledekSchematu, _slouc

    def sch(s, hodn):
        return VysledekSchematu(s, {k: PosudekZat(k, v, "V" if v is not None else "neomezuje",
                                                  0.5, 0.1, s) for k, v in hodn.items()},
                                10.0, 100.0, 1, None)

    vn = _slouc("Vn", {"dvojnaprava": sch("dvojnaprava", {"a": 20.0, "b": 12.0, "c": 13.0, "e": None}),
                       "naprava": sch("naprava", {"a": 18.0, "b": 10.0, "c": 18.0, "e": None})})
    assert [(p.V, p.schema) for p in vn] == [(20.0, "dvojnaprava"), (10.0, "naprava"),
                                              (16.0, "naprava"), (None, "dvojnaprava")]
    vr = _slouc("Vr", {"6": sch("6", {"a": 60.0, "b": 40.0, "c": 30.0, "e": 45.0}),
                       "2": sch("2", {"a": 1.0, "b": 14.0, "c": 20.0, "e": 30.0}),
                       "3": sch("3", {"a": 1.0, "b": 99.0, "c": 24.0, "e": 70.0})})
    assert [(p.V, p.schema) for p in vr] == [(60.0, "6"), (14.0, "2"), (24.0, "3"), (50.0, "3")]


def test_zatizitelnost_jen_normova_vozidla(d):
    from blc_posudek.zatizitelnost import zatizitelnost
    d2 = copy.deepcopy(d)
    d2["blc"]["vozidlo"] = "MLC_k"
    with pytest.raises(ValueError):
        zatizitelnost(d2)


def test_davka_zatizitelnost(tmp_path):
    from blc_posudek.__main__ import main
    assert main([PRIKLAD, "--zatizitelnost", "--druhy", "Ve", "--protokol", "vse",
                 "-o", str(tmp_path)]) == 0
    html = (tmp_path / "protokol.html").read_text(encoding="utf-8")
    assert "Zatížitelnost podle ČSN 73 6222" in html and "Ve – výjimečná (čl. 7.3)" in html
    assert (tmp_path / "obrazky" / "blc_pricny_Ve.png").exists()
    html = (tmp_path / "Ve" / "protokol.html").read_text(encoding="utf-8")   # jen Ve
    assert "Zatížitelnost Ve – výjimečná (ČSN 73 6222)" in html
    assert "Referenční Ve = 80 t – příčná poloha zatížení dopravou" in html


def test_davka_vice_souboru(tmp_path):
    """Více souborů (složka) → souhrn.csv; chyba jednoho souboru dávku nezastaví; -j 2."""
    import csv
    from blc_posudek.__main__ import main
    vstupy = tmp_path / "vstupy"
    vstupy.mkdir()
    text = open(PRIKLAD, encoding="utf-8").read()
    (vstupy / "a.toml").write_text(text, encoding="utf-8")
    (vstupy / "b.toml").write_text(text.replace("[blc]\n", "[blc]\ngama_Q = 1.5\n", 1),
                                   encoding="utf-8")
    out = tmp_path / "vystup"
    assert main([str(vstupy), "-o", str(out), "--bez-protokolu", "-j", "2"]) == 2   # b: chyba
    with open(out / "souhrn.csv", encoding="utf-8-sig") as f:
        radky = list(csv.DictReader(f, delimiter=";"))
    assert [r["soubor"] for r in radky] == ["a.toml", "b.toml"]
    a, b = radky
    assert a["nosnik"] == "N6" and a["vysledek"] == "NEVYHOVUJE" and a["chyba"] == ""
    assert a["eta_MSU [%]"].startswith("90,") and a["eta_MSP [%]"].startswith("111,")  # čárka
    assert b["vysledek"] == "CHYBA" and "gama_Q" in b["chyba"]
    assert not (out / "a" / "protokol.html").exists()                      # bez protokolu
    # jeden soubor bez protokolu: jen výpis
    assert main([str(vstupy / "a.toml"), "-o", str(tmp_path / "jeden"), "--bez-protokolu"]) == 1
    assert not (tmp_path / "jeden").exists()


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


@pytest.mark.skipif(not _tk(), reason="není k dispozici grafické prostředí")
def test_gui_soucinitele_na_karte_5():
    """Dílčí součinitele stálých zatížení, dopravy, chodců a teploty jsou všechny na kartě 5."""
    from blc_posudek.gui import AplikaceMost
    app = AplikaceMost(PRIKLAD)
    try:
        app.update()
        sekce = str(app.ram_soucinitele)
        for fm in (app.f_souc_stale, app.f_souc_doprava, app.f_souc_chodci, app.f_teplota_souc):
            assert str(fm).startswith(sekce)
        assert str(app.f_cas).split('.')[:3] == sekce.split('.')[:3]          # stejná karta jako čas. osa
        assert "gamma_Q" not in app.f_pred.prom and "gamma_G" not in app.f_nastaveni.prom
        assert app.f_souc_doprava.prom["psi0"].get() == "0.75"
        app.f_souc_doprava.prom["gamma_Q"].set("1.5")
        app.f_souc_chodci.prom["psi1_ch"].set("0.4")
        app.f_souc_stale.prom["gamma_G"].set("1.4")
        d = app.ziskej_data()
        assert d["blc"]["gamma_Q"] == 1.5 and d["blc"]["psi1_ch"] == 0.4
        assert d["posouzeni"]["gamma_G"] == 1.4
        assert parametry_blc(d)["soucinitele"].gamma_Q == 1.5
    finally:
        app.destroy()

