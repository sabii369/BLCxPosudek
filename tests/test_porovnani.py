"""Celý výpočet porovnani_zatizeni, síť MKP, grafy, prefabrikáty, spouštění."""
import subprocess
import sys

import numpy as np
import pytest
from pytest import approx

from blc import porovnani_zatizeni, __version__
from blc.geometry import E_betonu
from blc.prefabrikaty import nacti_prefabrikaty, prefabrikat
from conftest import KOREN


def test_rovnovaha_nosniky_2_pole():
    """Σ nosníků 2D = 1D statika spojitého nosníku ve všech řezech."""
    cr = porovnani_zatizeni(typ="k", MLC="MLC80", L=[10, 12], n=20, dist=30.5, Ve=80,
                            N=6, E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25, tisk=False)
    for r in cr.rezy:
        for st in (r.stav_MLC, r.stav_Ve):
            assert st.dM < 0.5 and st.dV < 0.5, r.rez.id


def test_tri_pole_rezy_a_obalky():
    cr = porovnani_zatizeni(typ="p", MLC="MLC60", L=[10, 14, 10], n=20, dist=30.5, Ve=60,
                            N=6, E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25, tisk=False)
    assert len(cr.rezy) == 3 + 2 + 6
    # obálka na nosníku ≈ hodnota v rozhodujícím stavu (obálka jen z mřížky poloh)
    for r in cr.rezy:
        if r.rez.typ == "M+":
            xs = cr.ob_MLC.xs
            maska = (xs >= r.rez.x_lo - 1e-9) & (xs <= r.rez.x_hi + 1e-9)
            assert cr.ob_MLC.M_max[r.k_MLC - 1][maska].max() == approx(r.MLC_2D, rel=0.03)


def test_spara_rovnovaha_a_beton_spary():
    assert E_betonu("C30/37") == approx(33000.0, rel=1e-12)
    cr = porovnani_zatizeni(typ="k", MLC="MLC80", L=[23, 23], n=15, dist=30.5, Ve=80,
                            N=6, beton="C45/55", Iy=0.094521, b=1.15, d=1.0, spara=True,
                            b_s=0.35, Iy_s=0.0202692, ex=0.25, tisk=False)
    assert all(st.dM < 0.5 and st.dV < 0.5 for r in cr.rezy for st in (r.stav_MLC, r.stav_Ve))
    cr2 = porovnani_zatizeni(typ="k", MLC="MLC80", L=[23], n=10, dist=30.5, Ve=80, N=4,
                             beton="C45/55", beton_s="C30/37", Iy=0.094521, b=1.15, spara=True,
                             b_s=0.35, Iy_s=0.0202692, ex=0.5, obalky=False, tisk=False)
    assert cr2.K.E_spary == approx(33000.0, rel=1e-12)


def test_sikma_deska_a_varovani():
    cr = porovnani_zatizeni(typ="k", MLC="MLC80", L=[12, 12], n=10, dist=30.5, Ve=80, N=1,
                            beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                            alfa=120, ex=0.5, krok_obalky=2.0, tisk=False)
    assert len(cr.rezy) == 2 + 1 + 4
    assert cr.rezy[0].jednotka == "kNm/m"
    crn = porovnani_zatizeni(typ="k", MLC="MLC40", L=[12], n=5, dist=30.5, Ve=40, N=4,
                             E=32000, Iy=0.0144, b=1.0, alfa=110, ex=0.5, obalky=False,
                             tisk=False)
    assert crn.varovani, "šikmé nosníky bez spáry mají zobrazit upozornění"


def test_vetknuti_cely_vypocet():
    cr = porovnani_zatizeni(typ="k", MLC="MLC40", L=[12, 12], n=5, dist=30.5, Ve=40, N=1,
                            beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                            alfa=110, uloz="vetknuti", k_rot=5e5, k_pod=2e6, ex=0.5,
                            obalky=True, krok_obalky=1.0, tisk=False)
    ids = [r.rez.id for r in cr.rezy]
    assert "M- podpora 1" in ids and "M- podpora 3" in ids
    assert cr.ob_MLC.M_min.min() < 0


@pytest.mark.parametrize("kw, plocha", [
    (dict(N=5, E=32000, Iy=0.0144, b=1.0, alfa=110, spara=True, b_s=0.3, Iy_s=0.003),
     (5 * 1.0 + 4 * 0.3) * 12.0),
    (dict(N=1, beton="C30/37", b=8.0, typ_konstrukce="deska", h=0.5, alfa=120), 8.0 * 12.0),
], ids=["nosniky", "deska"])
def test_sit_MKP_a_graf(kw, plocha):
    cr = porovnani_zatizeni(typ="k", MLC="MLC40", L=[12], n=5, dist=30.5, Ve=40, d=0.4,
                            ex=0.5, obalky=False, tisk=False, k_pod=2e6, **kw)
    S = cr.sit
    x, y = S.X[S.prvky], S.Y[S.prvky]
    A = 0.5 * np.abs(np.sum(x * np.roll(y, -1, 1) - np.roll(x, -1, 1) * y, axis=1))
    assert A.sum() == approx(plocha, rel=1e-9)
    assert S.k_uzlu is not None and len(S.podpory) == len(S.k_uzlu) > 0
    from blc.plotting import plot_sit
    plot_sit(cr, show=False)


def test_prefabrikaty_z_tabulky():
    tab, zdroj = nacti_prefabrikaty()
    assert zdroj.endswith("Prefabrikáty.xlsx"), "tabulka se má načíst z blc/data"
    assert len(tab) > 0
    p = prefabrikat("I-67 / 24")
    assert p is not None and p.spara and p.b == approx(1.15)


def test_spusteni_python_m_blc():
    out = subprocess.run([sys.executable, "-m", "blc", "--help"], cwd=KOREN,
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert "--demo" in out.stdout
    assert __version__
