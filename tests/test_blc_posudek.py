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
    kap = {k.nazev: [o.soubor for t, o in k.polozky if t == "obrazek"] for k in model.protokol.kapitoly}
    assert kap["Zatížení z modelu mostu (BLC)"] == ["blc_zat_stale", "blc_zat_q", "blc_zat_pricny",
                                                    "blc_sily"]
    tab = [o for t, o in next(k for k in model.protokol.kapitoly
                              if k.nazev == "Zatížení z modelu mostu (BLC)").polozky if t == "tabulka"]
    assert len(tab) == 2 + 6                               # součinitele, stavy, 6 kombinací
    # součinitele podle zadání: char, častá, kvazi, 6.10a, 6.10b, 6.10 × (G, doprava);
    # s Ve chodci nejsou (ČSN 73 6222, čl. 3.1.4)
    assert [r[1:] for r in tab[0].radky] == [
        ["1,00"] * 4, ["1,00", "1,00", "1,00", "0,75"], ["1,00", "1,00", "1,00", "0,00"],
        ["1,35", "1,00", "1,35", "0,75"], ["1,35", "0,85", "1,35", "1,00"],
        ["1,35", "1,00", "1,35", "1,00"]]
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
    assert "δ = 1.05 (ČSN 73 6222, čl. 8.4, výjimečná zatížitelnost)" in html
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
        assert "dyn" not in d["blc"] and "δ = 1.05 (ČSN 73 6222" in app.lbl_zat.cget("text")
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
    pol = m.blc["polohy"]
    assert pol["M"].plosne and len(pol["M"].platky) == 8           # 2 dvounápravy × 4 kola
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
    assert v2.vozidlo == "Ve 200.0 t"


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
    assert zat.druhy["Vn"].prvni.vys.q_ch == 2.5
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
        assert tit[2].startswith("zatížení chodců q_ch = 2.5 kN/m² (s Vn, Vr; s Ve chodci nejsou)")
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
