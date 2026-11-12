"""
Zatížitelnost podle ČSN 73 6222: zatěžovací pruhy, vozidla Vn / Vr, příčná poloha u užšího
chodníku, dynamické součinitele δ1–δ3 (obr. 8.1, tab. 8.1), zatížení chodců podle normy,
schéma Vn a vozidlo Vr na 2D modelu (obálka × rozhodující poloha, linearita).
"""
import math

import numpy as np
import pytest
from pytest import approx

from blc import schemata_zatizitelnosti as sz
from blc.dynamicky_soucinitel import (delta_i, delty_zatizitelnosti, dynamicky_soucinitel,
                                      nahradni_delka, vlastni_frekvence)
from blc.geometry import Konstrukce
from blc.stale_zatizeni import Vybaveni
from blc.vnitrni_sily import (_kombinuj_pruhy, polohy_q, vnitrni_sily, vys_pro_V,
                              vys_s_vozidlem)

L0 = 11.4
NOSNIKY = dict(L=L0, N=6, b=1.0, Iy=0.014375, beton="C35/45", d=0.55, A_nosniku=0.3, ex=0.125,
               krok=0.5, tisk=False)
VYB = Vybaveni(chodnik_L=1.0, chodnik_P=0.5, g_chodnik=5.0, g_vozovka=2.5)   # vozovka 1,0 … 5,5


# ---- norma: pruhy, vozidla, převody ----------------------------------------------

def test_zatezovaci_pruhy():
    assert sz.zatezovaci_pruhy(4.5) == (1, 3.0)
    assert sz.zatezovaci_pruhy(5.7) == (2, approx(2.85))           # 5,4 ≤ w ≤ 6 → 2 × 0,5·w
    assert sz.zatezovaci_pruhy(7.75) == (2, 3.0)
    assert sz.zatezovaci_pruhy(12.5) == (4, 3.0)


def test_Vn_z_vn():
    assert sz.Vn_z_vn(2.4) == approx(32.0)        # poznámka čl. 7.1.7: vn = 2,4 → Vn = 32 t
    assert sz.vn_z_Vn(32.0) == approx(2.4)
    assert sz.schema_Vn(16.0) == "dvojnaprava" and sz.schema_Vn(15.9) == "naprava"
    assert [sz.schema_Vr(v) for v in (12, 16, 30, 50, 51)] == ["2", "2", "3", "3", "6"]


def test_vozidla_vr():
    for v in sz.VOZIDLA_VR.values():
        assert sum(a.podil for a in v.napravy) == approx(1.0)
        assert all(0 < a.x < v.delka for a in v.napravy)
    assert sz.VOZIDLA_VR["6"].symetricke and not sz.VOZIDLA_VR["2"].symetricke
    assert [a.x for a in sz.VOZIDLA_VR["3"].napravy] == approx([1.5, 3.9, 5.1])


def test_pravidla_schemat():
    assert sz.Vn_ze_schemat(20.0) == 20.0
    assert sz.Vn_ze_schemat(12.0, 10.0) == 10.0
    assert sz.Vn_ze_schemat(12.0, 18.0) == 16.0       # náhradní náprava platí jen pod 16 t
    assert sz.Vn_ze_schemat(None) is None
    assert sz.Vr_ze_schemat(60.0) == 60.0
    assert sz.Vr_ze_schemat(40.0, 12.0) == 12.0
    assert sz.Vr_ze_schemat(40.0, 20.0, 25.0) == 25.0  # nad 16 t lze třínápravové
    assert sz.Vr_ze_schemat(40.0, 20.0, 18.0) == 20.0
    assert sz.Vr_ze_schemat(40.0, 30.0, 70.0) == 50.0  # nad 50 t platí šestinápravové
    assert sz.Vr_ze_schemat(None) is None


def test_pricna_poloha_u_uzsiho_chodniku():
    p = sz.pricna_poloha(1.5, 0.75, 10.0)
    assert (p.strana, p.y_kraj, p.smer, p.w) == ("P", 9.25, -1, approx(7.75))
    pruhy, zb = sz.pruhy_Vn(p, "dvojnaprava")
    assert [(r.y0, r.y1) for r in pruhy] == [(6.25, 9.25), (3.25, 6.25)]
    assert zb == (1.5, 3.25)
    assert [(r.naprava, r.F_kolo, r.q_rovnomerne) for r in pruhy] == [("dvojnaprava", 25.0, 2.5)] * 2
    assert sz.pruhy_Vn(p, "naprava")[0][0].F_kolo == 50.0          # náhradní náprava 100·vn
    q = sz.pricna_poloha(0.5, 1.0, 10.0)
    assert (q.strana, q.y_kraj) == ("L", 0.5)
    assert sz.pricna_poloha(1.0, 1.0, 10.0).strana == "L"          # shodné → levý kraj
    yc, y1, y2 = sz.stopy_vozidla_u_kraje(p, sz.VOZIDLA_VR["6"])
    assert (yc, y1, y2) == (7.75, 7.0, 8.5)                         # šířka vozidla 3,0 m
    p4 = sz.pricna_poloha(0.0, 0.0, 13.0)
    pr, zb = sz.pruhy_Vn(p4, "dvojnaprava")
    assert [r.naprava for r in pr] == ["dvojnaprava", "dvojnaprava", "jednoducha", "jednoducha"]
    assert [r.q_rovnomerne for r in pr] == [2.5, 2.5, 1.0, 1.0] and zb == (12.0, 13.0)


# ---- dynamické součinitele (kap. 8) ------------------------------------------------

def test_delta_obr_8_1():
    assert vlastni_frekvence(18.9) == approx(6.0, abs=0.02)        # zlomy obr. 8.1
    assert vlastni_frekvence(132.0) == approx(1.0, abs=0.01)
    assert [delta_i(i, 0.5) for i in (1, 2, 3)] == approx([1.20, 1.17, 1.13])
    assert [delta_i(i, 3.0) for i in (1, 2, 3)] == approx([1.40, 1.30, 1.20])
    assert [delta_i(i, 9.0) for i in (1, 2, 3)] == approx([1.25, 1.20, 1.15])
    assert delta_i(1, 5.25) == approx(1.325)                       # lineárně 4,5 – 6,0 Hz
    assert delta_i(4, 9.0) == delta_i(3, 9.0)


def test_nahradni_delka_a_delty():
    K = Konstrukce(L=[12.0], N=1, b=1.0, E=34000.0, Iy=0.05)
    assert nahradni_delka(K)[0] == approx(12.0)
    Ks = Konstrukce(L=[12.0], N=3, b=1.0, E=34000.0, Iy=0.05, alfa=110.0)
    assert nahradni_delka(Ks)[0] == approx(12.0 * math.sin(math.radians(70.0)))
    K2 = Konstrukce(L=[10.0, 14.0], N=1, b=1.0, E=34000.0, Iy=0.05)
    assert nahradni_delka(K2)[0] == approx(12.0)                   # průměr rozpětí
    d, zdroj = delty_zatizitelnosti(K)
    assert d == {1: 1.25, 2: 1.20, 3: 1.15} and "obr. 8.1" in zdroj
    assert delty_zatizitelnosti(K, 1.1)[0] == {1: 1.1, 2: 1.1, 3: 1.1}
    assert dynamicky_soucinitel("Vr", None, K)[0] == 1.25
    with pytest.raises(ValueError):
        dynamicky_soucinitel("Vr")


def test_kombinace_pruhu_delta():
    z = lambda v: {a + s: np.array([[v if s == "+" else -v]]) for a in ("M", "Vm", "Vp", "Vs")
                   for s in "+-"}
    dl = {1: 1.25, 2: 1.20, 3: 1.15}
    assert _kombinuj_pruhy([z(10.0), z(1.0)], None, dl)["M+"][0, 0] == approx(13.2)
    assert _kombinuj_pruhy([z(10.0), z(0.2)], None, dl)["M+"][0, 0] == approx(12.5)   # 1 pruh
    assert _kombinuj_pruhy([z(10.0), z(0.2)], z(2.0), dl)["M-"][0, 0] == approx(-15.0)


# ---- schéma Vn a vozidlo Vr na 2D modelu --------------------------------------------

@pytest.fixture(scope="module")
def vn():
    return vnitrni_sily(**NOSNIKY, vybaveni=VYB, Vn=32.0)


def test_Vn_schema(vn):
    assert vn.druh_q == "Vn" and vn.schema_q == "dvojnaprava" and vn.V == 32.0
    assert vn.q_ch == 2.5 and "qch" in vn.stavy                     # chodci podle tab. 7.1
    assert [(p["y0"], p["y1"], p["nazev"]) for p in vn.pruhy_q] == [
        (2.5, 5.5, "pruh 1"), (1.0, 2.5, "zbývající plocha")]       # 1 pruh u pravého kraje
    assert vn.obrys_q == []
    assert vn.dyn == 1.25 and "u pravého kraje vozovky" in vn.stavy["q"].popis
    assert not vn.varovani


def test_Vn_polohy_odpovidaji_obalce(vn):
    for o in range(vn.n_vyst):
        p = polohy_q(vn, o)
        t = vn.tabulka(o, "q")
        for k, a in (("M", "M_max"), ("V", "V_max")):
            i = int(np.argmin(np.abs(t.x - p[k].x)))
            assert p[k].hodnota == approx(getattr(t, a)[i], rel=1e-9, abs=1e-9)
    p = polohy_q(vn, 4)
    F_kola = sum(pl[0] for pl in p["M"].platky)
    assert F_kola == approx(4 * 25.0 * 2.4 * 1.25)                  # dvounáprava, 4 kola × δ1
    # rovnoměrné zatížení ve středu pole: celý pruh 2,5·vn + zbývající plocha vn
    q = sum((x1 - x0) * (y1 - y0) * qq for x0, x1, y0, y1, qq in p["M"].plosne)
    assert q == approx(1.25 * 2.4 * L0 * (2.5 * 3.0 + 1.5), rel=1e-6)


def test_Vn_linearita_a_prepocet(vn):
    v2 = vys_pro_V(vn, 16.0)
    assert v2.stavy["q"].M_max == approx(0.5 * vn.stavy["q"].M_max)
    assert v2.stavy["qch"] is vn.stavy["qch"] and v2.vozidlo == "Vn 16,0 t"
    assert polohy_q(v2, 2)["M"].hodnota == approx(0.5 * polohy_q(vn, 2)["M"].hodnota)
    ve = vys_s_vozidlem(vn, Ve=60.0)
    prima = vnitrni_sily(**NOSNIKY, vybaveni=VYB, Ve=60.0)
    assert ve.stavy["q"].M_max == approx(prima.stavy["q"].M_max)
    assert "qch" not in ve.stavy and ve.q_ch == 0.0                 # Ve: chodci vyloučeni
    assert vn.druh_q == "Vn" and "qch" in vn.stavy                  # originál beze změny
    nap = vys_s_vozidlem(vn, Vn=12.0)
    assert nap.schema_q == "naprava"
    p = polohy_q(nap, 4)
    assert len(p["M"].platky) == 2 and sum(pl[0] for pl in p["M"].platky) == approx(
        100.0 * sz.vn_z_Vn(12.0) * 1.25)                            # náhradní náprava 100·vn


def test_Vr_vozidlo_u_kraje(vn):
    vr = vys_s_vozidlem(vn, Vr=12.0)
    assert vr.schema_q == "2" and vr.dyn == 1.25 and vr.q_ch == 2.5
    assert vr.y_Ve == approx(5.5 - 1.25)                            # vnější okraj u kraje vozovky
    p = polohy_q(vr, 4)
    assert sum(pl[0] for pl in p["M"].platky) == approx(120.0 * 1.25)   # celé vozidlo × δ1
    t = vr.tabulka(4, "q")
    i = int(np.argmin(np.abs(t.x - p["M"].x)))
    assert p["M"].hodnota == approx(t.M_max[i], rel=1e-9)
    v6 = vys_s_vozidlem(vn, Vr=60.0)
    assert v6.schema_q == "6" and "šestinápravové" in v6.vozidlo
    # 3nápravové je při stejné tíze příznivější než 2nápravové (rozložení na víc náprav)
    v3 = vys_s_vozidlem(vn, Vr=20.0, schema="3")
    v2 = vys_s_vozidlem(vn, Vr=20.0, schema="2")
    assert v3.stavy["q"].M_max.max() < v2.stavy["q"].M_max.max()


def test_pricny_rez(vn):
    import matplotlib.pyplot as plt
    from blc.plotting_sily import plot_pricny_rez, popis_vozidla
    for v in (vn, vys_s_vozidlem(vn, Vr=60.0), vys_s_vozidlem(vn, Ve=80.0),
              vys_s_vozidlem(vn, MLC="MLC40")):
        fig = plot_pricny_rez(v, 2, show=False)
        ax = fig.axes[0]
        texty = " ".join(x.get_text() for x in ax.texts)
        assert "posuzovaný N3" in texty and len(ax.patches) > 10
        if v.druh_q in ("Vn", "Vr"):
            assert "kraj vozovky u užšího chodníku P" in texty
        plt.close(fig)
    vr = vys_s_vozidlem(vn, Vr=60.0)
    assert vr.obrys_q == [(2.5, 5.5)]                               # šířka 3 m u kraje 5,5 m
    assert "6 × 100 kN" in popis_vozidla(vr)
    assert vys_s_vozidlem(vn, Ve=80.0).obrys_q == [(1.75, 4.75)]    # osa vozovky 3,25 m


def test_chodci_podle_normy():
    v = vnitrni_sily(**NOSNIKY, vybaveni=VYB, MLC="MLC40")
    assert "qch" not in v.stavy and any("chodců pro MLC" in t for t in v.varovani)
    v = vnitrni_sily(**NOSNIKY, vybaveni=VYB, Vr=30.0, q_chodnik=0.0)
    assert "qch" not in v.stavy                                    # 0 = bez chodců
    v = vnitrni_sily(**NOSNIKY, vybaveni=VYB, Vr=30.0, q_chodnik=4.0)
    assert v.q_ch == 4.0 and v.q_ch_zdroj == "zadáno"
    with pytest.raises(ValueError):
        vnitrni_sily(**NOSNIKY, vybaveni=VYB, Vn=30.0, Ve=40.0)
