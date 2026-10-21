"""1D model spojitého nosníku (beam_1d.Nosnik1D) – analytická řešení."""
import numpy as np
import pytest
from pytest import approx

from blc.geometry import Konstrukce
from blc.beam_1d import Nosnik1D

E, IY = 32000, 0.0144


def nosnik(L, **kw):
    return Nosnik1D(Konstrukce(L=L, N=kw.pop("N", 15), b=1.0, E=E, Iy=IY, **kw))


def test_dve_pole_rovnomerne():
    L, q = 12.0, 10.0
    nos = nosnik([L, L])
    M, Vn, Vr, R = nos.stav([(q, 0.0, 2 * L)])
    assert R[0] == approx(3 * q * L / 8, rel=1e-3)
    assert R[1] == approx(10 * q * L / 8, rel=1e-3)
    assert R.sum() == approx(2 * q * L, rel=1e-9)
    assert M[nos.i_sup[1]] == approx(-q * L * L / 8, rel=1e-3)
    ii = nos.uzly_pole[0]
    assert M[ii].max() == approx(9 * q * L * L / 128, rel=1e-3)
    assert nos.xs[ii][int(np.argmax(M[ii]))] == approx(3 * L / 8, rel=0.02)


def test_tri_pole_rovnomerne():
    L, q = 10.0, 10.0
    nos = nosnik([L, L, L])
    M, Vn, Vr, R = nos.stav([(q, 0.0, 3 * L)])
    assert R[0] == approx(0.4 * q * L, rel=1e-3)
    assert R[1] == approx(1.1 * q * L, rel=1e-3)
    assert M[nos.i_sup[1]] == approx(-q * L * L / 10, rel=1e-3)


@pytest.mark.parametrize("typ, MLC", [("p", "MLC80"), ("k", "MLC40")])
def test_V_v_rezu_d_proti_prostemu_nosniku(typ, MLC):
    """V ve vzdálenosti d od podpory: zatížení smí stát i v pásu <0, d>."""
    L, d, roz = 12.0, 2.0, 0.5
    nos = Nosnik1D(Konstrukce(L=[L], N=15, b=1.0, E=E, Iy=IY, d=d))
    best_L = best_P = 0.0
    for ax0, ax in nos.stavy_MLC(typ, MLC, 60, 30.5, roz):
        Ra = lev_d = lev_Ld = 0.0
        for q, s_, e_ in ax:
            sc, ec = max(0.0, s_), min(L, e_)
            if ec > sc:
                F = q * (ec - sc); xm = 0.5 * (sc + ec)
                Ra += F * (L - xm) / L
                lev_d += q * max(0.0, min(ec, d) - sc)
                lev_Ld += q * max(0.0, min(ec, L - d) - sc)
        best_L = max(best_L, abs(Ra - lev_d))
        best_P = max(best_P, abs(Ra - lev_Ld))
    res = nos.prohledej(nos.stavy_MLC(typ, MLC, 60, 30.5, roz))
    cV = {c.rez.id: c.hodnota for c in res.cile}
    assert cV["V podpora 1 vpravo"] == approx(best_L, rel=1e-6)
    assert cV["V podpora 2 vlevo"] == approx(best_P, rel=1e-6)


def test_pruzne_podpory():
    q, L = 10.0, 12.0
    # prostý nosník je staticky určitý → M nezávisí na k
    M, _, _, R = nosnik([L], N=5, k_pod=1e5).stav([(q, 0.0, L)])
    assert M.max() == approx(q * L * L / 8, rel=1e-3)
    zat = [(q, 0, 2 * L)]
    R_t = nosnik([L, L], N=5).stav(zat)[3]
    R_k = nosnik([L, L], N=5, k_pod=1e12).stav(zat)[3]
    R_p = nosnik([L, L], N=5, k_pod=2e4).stav(zat)[3]
    assert R_k[1] == approx(R_t[1], rel=1e-4)              # k → ∞ ≈ tuhá
    assert R_p.sum() == approx(2 * q * L, rel=1e-7)
    assert R_p[1] < 10 * q * L / 8                          # měkká podpora odlehčí střed


def test_vetknuti():
    L, q = 12.0, 10.0
    nos = nosnik([L], uloz="vetknuti")
    M = nos.stav([(q, 0.0, L)])[0]
    assert M[nos.i_sup[0]] == approx(-q * L * L / 12, rel=1e-3)
    assert M.max() == approx(q * L * L / 24, rel=1e-3)
    # pružné vetknutí
    kr = 1000.0
    K = Konstrukce(L=[L], N=15, b=1.0, E=E, Iy=IY, uloz="vetknuti", k_rot=kr)
    nos = Nosnik1D(K)
    M = nos.stav([(q, 0.0, L)])[0]
    assert M[nos.i_sup[0]] == approx(-q * L * L / 12 / (1 + 2 * K.EI_celk / (kr * K.B * L)),
                                     rel=1e-3)
    # dvě pole vetknutá, zatížené 1. pole
    K = Konstrukce(L=[L, L], N=15, b=1.0, E=E, Iy=IY, uloz="vetknuti")
    nos = Nosnik1D(K)
    M = nos.stav([(q, 0.0, L)])[0]
    assert M[nos.i_sup[1]] == approx(-q * L * L / 12, rel=1e-3)
    ids = [r.id for r in K.kontrolni_rezy() if r.typ == "M-"]
    assert ids == ["M- podpora 1", "M- podpora 2", "M- podpora 3"]


@pytest.mark.parametrize("k_rot, ref", [(1e14, "vetknuti"), (1e-6, "tvrde")])
def test_pruzne_vetknuti_limity(k_rot, ref):
    """k_rot → ∞ dává dokonalé vetknutí, k_rot → 0 kloub."""
    zat = [(10.0, 2.0, 15.0)]
    a = nosnik([12, 9], uloz="vetknuti", k_rot=k_rot).stav(zat)[0]
    b = nosnik([12, 9], uloz=ref).stav(zat)[0]
    assert np.abs(a).max() == approx(np.abs(b).max(), rel=1e-4)
