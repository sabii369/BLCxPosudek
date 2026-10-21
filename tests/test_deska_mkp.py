"""2D MKP model (plate_fem.DeskaMKP – nosníky, slab_fem.DeskaSikmaMKP – deska)."""
import numpy as np
import pytest
from pytest import approx

from blc.geometry import Konstrukce
from blc.beam_1d import Nosnik1D
from blc.plate_fem import DeskaMKP, reseni_stavu, platky_z_naprav, ke_mitc4, KAPPA
from blc.slab_fem import DeskaSikmaMKP, ke_mitc4_quad

E, IY = 32000, 0.0144
NAPRAVY = [(400, 5, 6), (400, 12, 13), (300, 20, 21)]
SPARA = dict(spara=True, b_s=0.3, Iy_s=0.003)


def stav_nosniku(al=90, sik="prava", spara=False, **kw):
    """Nosníky 12 + 14 m, N = 5, tři nápravy uprostřed šířky → (model, stav)."""
    kk = dict(L=[12, 14], N=5, b=1.0, E=E, Iy=IY, alfa=al, sikmost=sik, **kw)
    if spara:
        kk.update(SPARA)
    m = DeskaMKP(Konstrukce(**kk), ex=0.25)
    return m, reseni_stavu(m, NAPRAVY, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3)


def deska(L=(12,), b=8.0, ex=0.25, **kw):
    return DeskaSikmaMKP(Konstrukce(L=list(L), N=1, b=b, E=E, Iy=0, typ="deska", h=0.5, **kw),
                         ex=ex)


# ---------------------------------------------------------------- prvek, κ
def test_mitc4_obecny_ctyruhelnik_je_obdelnik():
    Kr = ke_mitc4(0.3, 0.2, 1000.0, 0.2, 5000.0)
    Kq = ke_mitc4_quad([0, 0.3, 0.3, 0], [0, 0, 0.2, 0.2], 1000.0, 0.2, 5000.0)
    assert np.abs(Kr - Kq).max() / np.abs(Kr).max() < 1e-12


def test_smykova_tuhost_kappa():
    """Tlustá deska L/h = 6: průhyb uprostřed = ohyb + smyk (Timošenko, κ = 5/6)."""
    assert KAPPA == approx(5 / 6, rel=1e-12)
    L, B, h, Eb, q = 6.0, 2.0, 1.0, 30000.0, 10.0
    m = DeskaSikmaMKP(Konstrukce(L=[L], N=1, b=B, E=Eb, Iy=0.0, typ="deska", h=h, nu=0.0),
                      ex=0.0625)
    u = m.res(m.zatizeni([(q * L * B, 0.0, L, 0.0, B)]))
    k = int(np.argmin(np.abs(m.xs - L / 2)))
    w = float(np.mean(u[np.arange(m._ng) * m.nx + k]))
    Ek = Eb * 1000.0
    EI, GA = Ek * B * h ** 3 / 12, KAPPA * Ek / 2 * B * h
    w_b, w_s = 5 * q * B * L ** 4 / (384 * EI), q * B * L ** 2 / (8 * GA)
    assert w == approx(w_b + w_s, rel=0.01)


# ---------------------------------------------------------------- deska
def test_deska_rovnomerne_qL2_8():
    m = deska()
    M = m.vysledky(m.zatizeni([(10 * 20 * 8, -4, 16, 0, 8)]))[0]
    k = int(np.argmin(np.abs(m.xs - 6.0)))
    assert M[:, k].sum() / 8.0 == approx(180.0, rel=0.01)
    st = reseni_stavu(m, [(400, 5, 6)], 3.0, 5.0, 0.6, 0.3)
    assert st.dM < 2.0 and st.dV < 2.0


def _M_desky(al, sik="prava"):
    m = deska(alfa=al, sikmost=sik)
    M = m.vysledky(m.zatizeni([(10 * 40 * 8, -14, 26, 0, 8)]))[0]
    return (m.vyst.S @ M).max()


def test_deska_spojitost_sikmosti():
    assert _M_desky(90.5) == approx(_M_desky(90), rel=0.01)
    assert _M_desky(120, "leva") == approx(_M_desky(120, "prava"), rel=1e-6)


# ---------------------------------------------------------------- nosníky, šikmost
@pytest.mark.parametrize("spara", [False, True])
def test_sikme_nosniky(spara):
    _, s120 = stav_nosniku(120, spara=spara)
    assert s120.dM < 1e-6 and s120.dV < 1e-6                      # Σ pruhů = statika
    assert stav_nosniku(120, "leva", spara)[1].M.max() == approx(s120.M.max(), rel=1e-4)
    if spara:      # bez spáry je vliv šikmosti nadsazený (program varuje)
        assert stav_nosniku(91, spara=True)[1].M.max() == approx(
            stav_nosniku(90, spara=True)[1].M.max(), rel=0.02)


# ---------------------------------------------------------------- spára
@pytest.mark.parametrize("al", [90, 110])
@pytest.mark.parametrize("kv", [None, 2e6])
def test_spara_nema_vlastni_podporu(al, kv):
    """Podepřené uzly leží jen na nosnících, pružiny mají celkovou délku N·b."""
    N, b = 4, 1.0
    K = Konstrukce(L=[10, 12], N=N, b=b, E=E, Iy=IY, alfa=al, k_pod=kv,
                   spara=True, b_s=0.35, Iy_s=0.004)
    m = DeskaMKP(K, ex=0.25)
    g_nos = set()
    for s_ in m.i_nos:
        g_nos.update(range(m.p_g0[s_], m.p_g0[s_] + m.p_ney[s_] + 1))
    g_pod = set(int(g) for g in m.reac_dof // m.nx)
    assert g_pod <= g_nos
    assert len(m.reac_dof) == N * (m.ney + 1) * (K.n_poli + 1)
    if kv:
        delka = np.bincount(m.reac_j, weights=m.k_uzlu) / kv
        assert np.allclose(delka, N * b)
        assert K.delka_podpory == approx(N * b, abs=1e-12)


def test_spara_spojitost_90():
    def st(al):
        m = DeskaMKP(Konstrukce(L=[12, 14], N=5, b=1.0, E=E, Iy=IY, alfa=al,
                                spara=True, b_s=0.3, Iy_s=0.003), ex=0.25)
        s_ = reseni_stavu(m, NAPRAVY, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3)
        return s_.M.max(), max(np.abs(s_.Vp).max(), np.abs(s_.Vm).max())
    (M90, V90), (M9002, V9002) = st(90), st(90.02)
    assert M9002 == approx(M90, rel=1e-3)
    assert V9002 == approx(V90, rel=1e-3)


def test_spara_stejna_jako_nosnik_a_beton_spary():
    N, b = 4, 1.0
    ax = [(300.0, 4.0, 4.5), (300.0, 13.0, 13.5)]

    def st(**kw):
        K = Konstrukce(L=[10, 12], N=N, b=b, E=E, Iy=IY, spara=True, b_s=b, Iy_s=IY, **kw)
        return reseni_stavu(DeskaMKP(K, ex=0.25), ax, 2.3, 4.1, 0.6, 0.3)
    ss = st()
    assert ss.dM < 1e-6 and ss.dV < 1e-6
    assert ss.R.sum() == approx(2 * 300.0 * 0.5, rel=1e-9)
    se = st(E_s=E)                                  # E_s = E ≡ nezadané E_s
    assert np.abs(se.M - ss.M).max() < 1e-12
    sm = st(E_s=E / 2)                              # měkčí spára nese méně
    assert np.abs(sm.Ms).max() < np.abs(ss.Ms).max()
    assert sm.dM < 1e-6 and sm.dV < 1e-6


# ---------------------------------------------------------------- pružné podpory
def test_pruzne_podpory_nosniky_kolme():
    _, s0 = stav_nosniku(spara=True)
    _, s1 = stav_nosniku(spara=True, k_pod=1e12)
    _, s2 = stav_nosniku(spara=True, k_pod=2e6)
    assert s1.M.max() == approx(s0.M.max(), rel=1e-4)
    assert np.abs(s1.Vp).max() == approx(np.abs(s0.Vp).max(), rel=1e-3)
    assert s2.M.max() == approx(s0.M.max(), rel=0.01)
    assert s2.R.sum() == approx(2 * 400 + 300, rel=1e-6)
    assert s2.dM < 1e-6 and s2.dV < 1e-6


def test_pruzne_podpory_nosniky_sikme():
    _, st_t = stav_nosniku(120, spara=True)
    _, st_k = stav_nosniku(120, spara=True, k_pod=1e12)
    m, st_p = stav_nosniku(120, spara=True, k_pod=2e6)
    assert st_k.R[0] == approx(st_t.R[0], rel=1e-3)
    assert np.abs(st_k.Vp).max() == approx(np.abs(st_t.Vp).max(), rel=2e-3)
    assert st_p.M.max() == approx(st_t.M.max(), rel=0.03)
    assert st_p.dM < 1e-6
    f = m.zatizeni(platky_z_naprav(NAPRAVY, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3))
    assert np.all(np.isfinite(m.reakce_uzlu(f, m.res(f))))


def test_pruzne_podpory_deska_sikma():
    def st(k):
        m = deska(ex=0.5, alfa=120, k_pod=k)
        return m, reseni_stavu(m, NAPRAVY[:2], 3.0, 5.0, 0.5, 0.3)
    _, sd0 = st(None)
    _, sd1 = st(1e12)
    md2, sd2 = st(2e6)
    assert sd1.M.max() == approx(sd0.M.max(), rel=1e-3)
    f2 = md2.zatizeni(platky_z_naprav(NAPRAVY[:2], 3.0, 5.0, 0.5, 0.3))
    assert sd2.R.sum() == approx(f2.sum(), rel=1e-6)
    assert sd2.M.max() == approx(sd0.M.max(), rel=0.05)


# ---------------------------------------------------------------- okrajové podmínky
@pytest.mark.parametrize("spara", [False, True], ids=["bez_spary", "se_sparou"])
@pytest.mark.parametrize("uloz, k_rot, k_v", [("vetknuti", None, None), ("vetknuti", 5e5, None),
                                              ("vetknuti", None, 2e6), ("mekke", None, None)])
def test_okrajove_podminky_nosniky_2D_vs_1D(spara, uloz, k_rot, k_v):
    """Σ pruhů 2D = 1D model. Se spárou ±1 %: spára vlastní podporu nemá, 1D vetkne
    celý průřez včetně Iy spár → 2D nad krajní podporou o ~0,3–0,6 % menší |M|."""
    tol = 1e-2 if spara else 5e-3
    nap = [(400 / 0.5, 3.0, 3.5), (400 / 0.5, 7.0, 7.5), (300 / 0.5, 15.0, 15.5)]
    K = Konstrukce(L=[12, 10], N=5, b=1.0, E=E, Iy=IY, uloz=uloz, k_rot=k_rot, k_pod=k_v,
                   **(SPARA if spara else {}))
    m = DeskaMKP(K, ex=0.25)
    s_ = reseni_stavu(m, nap, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.0)
    nos = Nosnik1D(K)
    M1, _, _, R1 = nos.stav(nap)
    sM = s_.P_M.sum(axis=0)
    assert sM[m.p_sup[0, 1]] == approx(M1[nos.i_sup[1]], rel=tol)
    if K.vetknuti:
        assert sM[m.p_sup[0, 0]] == approx(M1[nos.i_sup[0]], rel=tol)
    assert s_.R[0] == approx(R1[0], rel=tol)
    assert s_.dM < 1e-6 and s_.dV < 1e-6


def test_deska_kolma_vetknuta_vs_1D():
    K = Konstrukce(L=[12, 10], N=1, b=8.0, E=E, Iy=0, typ="deska", h=0.5, uloz="vetknuti")
    m = DeskaSikmaMKP(K, ex=0.25)
    sM = m.vyslednice(m.res(m.zatizeni([(1200.0, 3.0, 9.0, 0.0, 8.0)])))[0].sum(axis=0)
    M1 = Nosnik1D(K).stav([(200.0, 3.0, 9.0)])[0]
    assert sM[m.k_sup[0]] == approx(M1[0], rel=0.01)
    assert sM.max() == approx(M1.max(), rel=0.015)


def _V_tupy_roh(k, uloz="tvrde"):
    """Šikmá deska 105°: max |V| v pásu y = 0 … 1 m u tupého rohu."""
    K = Konstrukce(L=[20], N=1, b=10.0, E=34000, Iy=0, typ="deska", h=0.5, alfa=105,
                   k_pod=k, uloz=uloz)
    m = DeskaSikmaMKP(K, ex=0.25)
    f = m.zatizeni([(600.0, 0.4 + K.x0(1.5), 1.4 + K.x0(1.5), 0.6, 2.4)])
    _, Vm, Vp = m.vyslednice(m.res(f))
    return float(np.abs((0.5 * (Vm + Vp))[:4].sum(axis=0)).max())


def test_sikma_deska_V_u_tupeho_rohu():
    """β_s = ∂w/∂s u pružné podpory → V u tupého rohu plynule přechází k tuhé podpoře
    (se zjednodušenou vazbou β_s = 0 by parazitní smyk V zvětšil o ~30 %)."""
    v0 = _V_tupy_roh(None)
    assert _V_tupy_roh(1e8) == approx(v0, rel=5e-3)
    assert _V_tupy_roh(2e6) == approx(v0, rel=0.05)
    assert abs(_V_tupy_roh(None, "mekke") - v0) > 1e-6
