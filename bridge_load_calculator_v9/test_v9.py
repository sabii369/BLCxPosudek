"""
test_v9.py – ověřovací testy verze v9 (testy v8 + okrajové podmínky podpor).
13. 10. 2026: spára vlastní podporu nemá nikdy (ani u kolmého mostu) – test 7
upraven (dříve „spára ≡ nosník“ s podepřenou spárou), regrese v7 jen bez spáry.

Spuštění:  python test_v9.py
"""
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge_load_calculator_v9 import porovnani_zatizeni
from bridge_load_calculator_v9.geometry import Konstrukce
from bridge_load_calculator_v9.beam_1d import Nosnik1D

OK, FAIL = "  OK  ", " CHYBA"
vysledky = []


def kontrola(nazev, hodnota, ocekavano, tol):
    chyba = abs(hodnota - ocekavano) / max(abs(ocekavano), 1e-12)
    ok = chyba <= tol
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] {nazev}: {hodnota:.4f} (očekáváno {ocekavano:.4f}, "
          f"rozdíl {100 * chyba:.4f} %, tol. {100 * tol:.2f} %)")


def test_analytika_dve_pole():
    print("\n1) Dvě stejná pole, rovnoměrné zatížení q (analytické řešení)")
    L, q = 12.0, 10.0
    K = Konstrukce(L=[L, L], N=15, b=1.0, E=32000, Iy=0.0144)
    nos = Nosnik1D(K)
    M, Vn, Vr, R = nos.stav([(q, 0.0, 2 * L)])
    kontrola("reakce koncová 3qL/8", R[0], 3 * q * L / 8, 1e-3)
    kontrola("reakce střední 10qL/8", R[1], 10 * q * L / 8, 1e-3)
    kontrola("suma reakcí = zatížení", R.sum(), 2 * q * L, 1e-9)
    kontrola("M nad podporou −qL²/8", M[nos.i_sup[1]], -q * L * L / 8, 1e-3)
    ii = nos.uzly_pole[0]
    kontrola("M max v poli 9qL²/128", M[ii].max(), 9 * q * L * L / 128, 1e-3)
    kontrola("poloha max M = 3L/8", nos.xs[ii][int(np.argmax(M[ii]))], 3 * L / 8, 0.02)


def test_analytika_tri_pole():
    print("\n2) Tři stejná pole, rovnoměrné zatížení (analytické řešení)")
    L, q = 10.0, 10.0
    K = Konstrukce(L=[L, L, L], N=15, b=1.0, E=32000, Iy=0.0144)
    nos = Nosnik1D(K)
    M, Vn, Vr, R = nos.stav([(q, 0.0, 3 * L)])
    kontrola("reakce koncová 0,4 qL", R[0], 0.4 * q * L, 1e-3)
    kontrola("reakce vnitřní 1,1 qL", R[1], 1.1 * q * L, 1e-3)
    kontrola("M nad podporou −qL²/10", M[nos.i_sup[1]], -q * L * L / 10, 1e-3)


def test_regrese_v5():
    print("\n3) Regrese: jedno pole dává výsledky v5")
    try:
        import bridge_load_calculator_v5 as v5
    except ImportError:
        print("   (balíček v5 není v cestě — test přeskočen)")
        return
    import bridge_load_calculator_v9 as v7
    for typ, MLC, d in (("p", "MLC80", 0.0), ("p", "MLC80", 2.0), ("k", "MLC40", 2.0)):
        kw = dict(typ=typ, MLC=MLC, n=60, dist=30.5, Ve=80, N=15, E=32000, Iy=0.0144,
                  b=1, nu=0.2, ex=0.25, tisk=False)
        a = v5.porovnani_zatizeni(L=12, d=d, **kw)
        b = v7.porovnani_zatizeni(L=12, d=d, **kw)
        Mz = [r for r in b.rezy if r.rez.typ == "M+"][0]
        Vs = [r for r in b.rezy if r.rez.typ == "V"]
        print(f"   {MLC} {typ}, d = {d}")
        kontrola("  1D Mmax MLC", Mz.MLC_1D, a.Mmax_MLC, 1e-3)
        if d == 0:     # v5 pro d > 0 vylučovala zatížení v <0,d>, v7 už ne
            kontrola("  1D Vmax MLC", max(r.MLC_1D for r in Vs), a.Vmax_MLC, 1e-3)
        kontrola("  2D M nosník MLC", Mz.MLC_2D, a.fp_MLC.M_max, 5e-3)


def test_rovnovaha_deska():
    print("\n4) Rovnováha 2D desky: Σ nosníků = 1D statika spojitého nosníku")
    cr = porovnani_zatizeni(typ="k", MLC="MLC80", L=[10, 12], n=20, dist=30.5, Ve=80,
                            N=6, E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25, tisk=False)
    for r in cr.rezy:
        for nazev, st in (("MLC", r.stav_MLC), ("Ve", r.stav_Ve)):
            ok = st.dM < 0.5 and st.dV < 0.5
            vysledky.append(ok)
            print(f"[{OK if ok else FAIL}] {r.rez.id:<22} {nazev:<4} "
                  f"odchylka M {st.dM:.4f} %   V {st.dV:.4f} %")


def test_tri_pole_zona_obalky():
    print("\n5) Tři pole: řezy a obálky na nosnících")
    t = time.time()
    cr = porovnani_zatizeni(typ="p", MLC="MLC60", L=[10, 14, 10], n=20, dist=30.5, Ve=60,
                            N=6, E=32000, Iy=0.0144, b=1.0, d=0.5, ex=0.25, tisk=False)
    ok = len(cr.rezy) == 3 + 2 + 6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] 3 pole: {len(cr.rezy)} kontrolních řezů, {time.time() - t:.1f} s")
    # obálka na nosníku ≥ hodnota v rozhodujícím stavu (M+; obálka jen z mřížky poloh)
    for r in cr.rezy:
        if r.rez.typ == "M+":
            k = r.k_MLC - 1
            xs = cr.ob_MLC.xs
            maska = (xs >= r.rez.x_lo - 1e-9) & (xs <= r.rez.x_hi + 1e-9)
            ob = cr.ob_MLC.M_max[k][maska].max()
            kontrola(f"obálka M nosník {k + 1} vs stav {r.rez.id}", ob, r.MLC_2D, 0.03)


def test_V_v_rezu_d():
    print("\n6) V v řezu d: zatížení i v pásu u podpory, kontrola proti prostému nosníku")
    L, d = 12.0, 2.0
    from bridge_load_calculator_v9.beam_1d import rozsir
    K = Konstrukce(L=[L], N=15, b=1.0, E=32000, Iy=0.0144, d=d)
    nos = Nosnik1D(K)
    for typ, MLC in (("p", "MLC80"), ("k", "MLC40")):
        roz = 0.5
        best_L = best_P = 0.0
        v_pasu = False
        for ax0, ax in nos.stavy_MLC(typ, MLC, 60, 30.5, roz):
            Ra = 0.0; lev_d = 0.0; lev_Ld = 0.0
            for q, s_, e_ in ax:
                sc, ec = max(0.0, s_), min(L, e_)
                if ec > sc:
                    F = q * (ec - sc); xm = 0.5 * (sc + ec)
                    Ra += F * (L - xm) / L
                    lev_d += q * max(0.0, min(ec, d) - sc)
                    lev_Ld += q * max(0.0, min(ec, L - d) - sc)
            vL, vP = abs(Ra - lev_d), abs(Ra - lev_Ld)
            if vL > best_L:
                best_L = vL
                v_pasu = any(max(0.0, s_) < d and e_ > 0 for q, s_, e_ in ax)
            best_P = max(best_P, vP)
        res = nos.prohledej(nos.stavy_MLC(typ, MLC, 60, 30.5, roz))
        cV = {c.rez.id: c.hodnota for c in res.cile}
        kontrola(f"{MLC} V(x = d)     ", cV["V podpora 1 vpravo"], best_L, 1e-6)
        kontrola(f"{MLC} V(x = L − d) ", cV["V podpora 2 vlevo"], best_P, 1e-6)
        print(f"         rozhodující poloha má zatížení v pásu <0, d>: {'ano' if v_pasu else 'ne'}")


def test_spara():
    print("\n7) Podélná spára: rovnováha, spára bez podpory (kolmý i šikmý most), spojitost α → 90°")
    from bridge_load_calculator_v9.geometry import E_betonu
    from bridge_load_calculator_v9.plate_fem import DeskaMKP, reseni_stavu
    kontrola("E pro C30/37 = 33 000 MPa", E_betonu("C30/37"), 33000.0, 1e-12)
    cr = porovnani_zatizeni(typ="k", MLC="MLC80", L=[23, 23], n=15, dist=30.5, Ve=80,
                            N=6, beton="C45/55", Iy=0.094521, b=1.15, d=1.0, spara=True,
                            b_s=0.35, Iy_s=0.0202692, ex=0.25, tisk=False)
    ok = all(st.dM < 0.5 and st.dV < 0.5 for r in cr.rezy for st in (r.stav_MLC, r.stav_Ve))
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] spára: Σ nosníků + spár = 1D statika ve všech řezech")
    # podepřeny jsou vždy jen nosníky – spára vlastní podporu nemá (kolmý i šikmý
    # most, tuhé i pružné podpory): podepřené uzly leží jen na podélných čarách
    # nosníků, pružiny mají celkovou délku N·b
    N, b, Iy = 4, 1.0, 0.0144
    for al in (90, 110):
        for kv in (None, 2e6):
            Kp = Konstrukce(L=[10, 12], N=N, b=b, E=32000, Iy=Iy, alfa=al, k_pod=kv,
                            spara=True, b_s=0.35, Iy_s=0.004)
            mp = DeskaMKP(Kp, ex=0.25)
            g_nos = set()
            for s_ in mp.i_nos:
                g_nos.update(range(mp.p_g0[s_], mp.p_g0[s_] + mp.p_ney[s_] + 1))
            g_pod = set(int(g) for g in mp.reac_dof // mp.nx)
            n_ocek = N * (mp.ney + 1) * (Kp.n_poli + 1)
            ok = g_pod <= g_nos and len(mp.reac_dof) == n_ocek
            if kv:
                tr = np.bincount(mp.reac_j, weights=mp.k_uzlu) / kv
                ok = ok and np.allclose(tr, N * b) and abs(Kp.delka_podpory - N * b) < 1e-12
            vysledky.append(ok)
            print(f"[{OK if ok else FAIL}] spára bez podpory (α {al}°, "
                  f"{'k_v' if kv else 'tuhé'}): {len(mp.reac_dof)} podepřených uzlů jen na "
                  f"nosnících (očekáváno {n_ocek})"
                  + (f", délka pružin {tr[0]:.3f} m = N·b" if kv else ""))
    # spojitost α → 90° se spárou (do 13. 10. 2026 byla u 90° spára podepřena,
    # u šikmého mostu ne → skok V nosníků o ~6 %)
    def st_sp(al):
        m = DeskaMKP(Konstrukce(L=[12, 14], N=5, b=1.0, E=32000, Iy=0.0144, alfa=al,
                                spara=True, b_s=0.3, Iy_s=0.003), ex=0.25)
        st_ = reseni_stavu(m, [(400, 5, 6), (400, 12, 13), (300, 20, 21)],
                           0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3)
        return st_.M.max(), max(np.abs(st_.Vp).max(), np.abs(st_.Vm).max())
    (M90, V90), (M9002, V9002) = st_sp(90), st_sp(90.02)
    kontrola("spára: α = 90,02° ≈ 90° (max M nosníků)", M9002, M90, 1e-3)
    kontrola("spára: α = 90,02° ≈ 90° (max |V| nosníků)", V9002, V90, 1e-3)
    Ks = Konstrukce(L=[10, 12], N=N, b=b, E=32000, Iy=Iy, spara=True, b_s=b, Iy_s=Iy)
    ms = DeskaMKP(Ks, ex=0.25)
    ax = [(300.0, 4.0, 4.5), (300.0, 13.0, 13.5)]
    ss = reseni_stavu(ms, ax, 2.3, 4.1, 0.6, 0.3)
    ok = ss.dM < 1e-6 and ss.dV < 1e-6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] spára b_s = b: Σ pruhů = statika "
          f"(M {ss.dM:.1e} %, V {ss.dV:.1e} %)")
    kontrola("spára b_s = b: Σ reakcí = zatížení", ss.R.sum(), 2 * 300.0 * 0.5, 1e-9)
    # beton spáry: E_s = E dává totéž jako nezadaný; měkčí spára nese méně
    Ke = Konstrukce(L=[10, 12], N=N, b=b, E=32000, Iy=Iy, spara=True, b_s=b, Iy_s=Iy, E_s=32000)
    se = reseni_stavu(DeskaMKP(Ke, ex=0.25), ax, 2.3, 4.1, 0.6, 0.3)
    kontrola("E_s = E ≡ bez zadání E_s (M nosníků)", 1.0 + np.abs(se.M - ss.M).max(), 1.0, 1e-12)
    Km = Konstrukce(L=[10, 12], N=N, b=b, E=32000, Iy=Iy, spara=True, b_s=b, Iy_s=Iy, E_s=16000)
    sm = reseni_stavu(DeskaMKP(Km, ex=0.25), ax, 2.3, 4.1, 0.6, 0.3)
    ok = np.abs(sm.Ms).max() < np.abs(ss.Ms).max() and sm.dM < 1e-6 and sm.dV < 1e-6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] E_s = E/2: spáry nesou méně "
          f"({np.abs(sm.Ms).max():.1f} < {np.abs(ss.Ms).max():.1f} kNm), rovnováha drží")
    cr2 = porovnani_zatizeni(typ="k", MLC="MLC80", L=[23], n=10, dist=30.5, Ve=80, N=4,
                             beton="C45/55", beton_s="C30/37", Iy=0.094521, b=1.15, spara=True,
                             b_s=0.35, Iy_s=0.0202692, ex=0.5, obalky=False, tisk=False)
    kontrola("beton spáry C30/37 → E_s", cr2.K.E_spary, 33000.0, 1e-12)


def test_v8():
    print("\n8) v8: regrese v7, deska, šikmost")
    import bridge_load_calculator_v9 as v8
    try:
        import bridge_load_calculator_v7 as v7
    except ImportError:
        v7 = None
    kw = dict(typ="k", MLC="MLC80", L=[12, 14], n=15, dist=30.5, Ve=80, N=5, E=32000,
              Iy=0.0144, b=1.0, d=0.5, ex=0.25, obalky=False, tisk=False)
    if v7 is not None:
        # v7 měla smykovou tuhost 6·G·h, v8 κ·G·h (κ = 5/6) → v7 se pro srovnání
        # přepočte se stejnou smykovou tuhostí
        import bridge_load_calculator_v7.plate_fem as pf7
        from bridge_load_calculator_v9.plate_fem import KAPPA
        ke7 = pf7.ke_mitc4
        pf7.ke_mitc4 = lambda a_, c_, D_, nu_, kGh_: ke7(a_, c_, D_, nu_, kGh_ * KAPPA / 6.0)
        # jen bez spáry: v7 podpírala spáru u kolmého mostu, v9 (od 13. 10. 2026)
        # spára vlastní podporu nemá
        for extra in ({},):
            a = v7.porovnani_zatizeni(**kw, **extra)
            b = v8.porovnani_zatizeni(**kw, **extra)
            dmax = max(max(abs(ra.MLC_2D - rb.MLC_2D), abs(ra.Ve_2D - rb.Ve_2D))
                       for ra, rb in zip(a.rezy, b.rezy))
            kontrola(f"v8 = v7 (kolmé nosníky{', spára' if extra else ''}), max rozdíl",
                     1.0 + dmax, 1.0, 1e-6)
        pf7.ke_mitc4 = ke7
    from bridge_load_calculator_v9.plate_fem import ke_mitc4, DeskaMKP, reseni_stavu
    from bridge_load_calculator_v9.slab_fem import ke_mitc4_quad, DeskaSikmaMKP
    Kr = ke_mitc4(0.3, 0.2, 1000.0, 0.2, 5000.0)
    Kq = ke_mitc4_quad([0, 0.3, 0.3, 0], [0, 0, 0.2, 0.2], 1000.0, 0.2, 5000.0)
    kontrola("MITC4 obecný čtyřúhelník = obdélník", 1.0 + np.abs(Kr - Kq).max() / np.abs(Kr).max(),
             1.0, 1e-12)
    # deska, rovnoměrné zatížení: průměr m_x přes šířku = qL²/8
    K = Konstrukce(L=[12], N=1, b=8.0, E=32000, Iy=0, typ="deska", h=0.5)
    m = DeskaSikmaMKP(K, ex=0.25)
    f = m.zatizeni([(10 * 20 * 8, -4, 16, 0, 8)])
    M, Vm, Vp, u = m.vysledky(f)
    k = int(np.argmin(np.abs(m.xs - 6.0)))
    kontrola("deska: průměr m_x uprostřed = qL²/8", M[:, k].sum() / 8.0, 180.0, 0.01)
    st = reseni_stavu(m, [(400, 5, 6)], 3.0, 5.0, 0.6, 0.3)
    ok = st.dM < 2.0 and st.dV < 2.0
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] kolmá deska: Σ pruhů vs statika M {st.dM:.2f} %, V {st.dV:.2f} %")
    # spojitost pro α → 90°
    def M_desky(al, sik="prava"):
        K = Konstrukce(L=[12], N=1, b=8.0, E=32000, Iy=0, typ="deska", h=0.5,
                       alfa=al, sikmost=sik)
        m = DeskaSikmaMKP(K, ex=0.25)
        f = m.zatizeni([(10 * 40 * 8, -14, 26, 0, 8)])
        M = m.vysledky(f)[0]
        return (m.vyst.S @ M).max()
    kontrola("deska α = 90,5° ≈ 90°", M_desky(90.5), M_desky(90), 0.01)
    kontrola("deska šikmá: pravá = levá (symetrické zatížení)", M_desky(120, "leva"),
             M_desky(120, "prava"), 1e-6)

    def st_nos(al, sik="prava", sp=False):
        kk = dict(L=[12, 14], N=5, b=1.0, E=32000, Iy=0.0144, alfa=al, sikmost=sik)
        if sp:
            kk.update(spara=True, b_s=0.3, Iy_s=0.003)
        m = DeskaMKP(Konstrukce(**kk), ex=0.25)
        B = m.B
        return reseni_stavu(m, [(400, 5, 6), (400, 12, 13), (300, 20, 21)],
                            0.5 * B - 1.0, 0.5 * B + 1.0, 0.5, 0.3)
    for sp in (False, True):
        s60 = st_nos(120, sp=sp)
        ok = s60.dM < 1e-6 and s60.dV < 1e-6
        vysledky.append(ok)
        print(f"[{OK if ok else FAIL}] šikmé nosníky 120°{' se spárou' if sp else ''}: "
              f"Σ = statika (M {s60.dM:.1e} %, V {s60.dV:.1e} %)")
        if sp:      # bez spáry je vliv šikmosti nadsazený (program varuje)
            kontrola("šikmé nosníky se spárou: 91° ≈ 90° (max M)",
                     st_nos(91, sp=sp).M.max(), st_nos(90, sp=sp).M.max(), 0.02)
        kontrola(f"šikmé nosníky{' se spárou' if sp else ''}: pravá = levá",
                 st_nos(120, "leva", sp).M.max(), s60.M.max(), 1e-4)
    cr = v8.porovnani_zatizeni(typ="k", MLC="MLC80", L=[12, 12], n=10, dist=30.5, Ve=80, N=1,
                               beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                               alfa=120, ex=0.5, krok_obalky=2.0, tisk=False)
    crn = v8.porovnani_zatizeni(typ="k", MLC="MLC40", L=[12], n=5, dist=30.5, Ve=40, N=4,
                                E=32000, Iy=0.0144, b=1.0, alfa=110, ex=0.5, obalky=False,
                                tisk=False)
    ok = bool(crn.varovani)
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] šikmé nosníky bez spáry: zobrazí se upozornění")
    ok = len(cr.rezy) == 2 + 1 + 4 and cr.rezy[0].jednotka == "kNm/m"
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] šikmá deska 2 pole: {len(cr.rezy)} řezů, "
          f"rozhoduje {cr.rozhodujici.rez.id} ({cr.max_vyuziti:.1f} %)")


def test_pruzna_podpora():
    print("\n9) Pružné svislé podpory k_v")
    from bridge_load_calculator_v9.plate_fem import DeskaMKP, reseni_stavu
    from bridge_load_calculator_v9.slab_fem import DeskaSikmaMKP
    q, L = 10.0, 12.0
    # 1D: prostý nosník je staticky určitý → M nezávisí na k
    nos = Nosnik1D(Konstrukce(L=[L], N=5, b=1.0, E=32000, Iy=0.0144, k_pod=1e5))
    M, _, _, R = nos.stav([(q, 0.0, L)])
    kontrola("1D prostý nosník, pružné podpory: M max = qL²/8", M.max(), q * L * L / 8, 1e-3)
    # 1D spojitý: k → ∞ ≈ tuhá, Σ R = zatížení
    nos_t = Nosnik1D(Konstrukce(L=[L, L], N=5, b=1.0, E=32000, Iy=0.0144))
    nos_k = Nosnik1D(Konstrukce(L=[L, L], N=5, b=1.0, E=32000, Iy=0.0144, k_pod=1e12))
    nos_p = Nosnik1D(Konstrukce(L=[L, L], N=5, b=1.0, E=32000, Iy=0.0144, k_pod=2e4))
    kontrola("1D 2 pole, k = 1e12 ≈ tuhá (střední reakce)",
             nos_k.stav([(q, 0, 2 * L)])[3][1], nos_t.stav([(q, 0, 2 * L)])[3][1], 1e-4)
    Rp = nos_p.stav([(q, 0, 2 * L)])[3]
    kontrola("1D 2 pole, pružné: Σ R = zatížení", Rp.sum(), 2 * q * L, 1e-7)
    ok = Rp[1] < 10 * q * L / 8
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] 1D 2 pole, měkká podpora: střední reakce klesne "
          f"({Rp[1]:.1f} < {10 * q * L / 8:.1f})")

    nap = [(400, 5, 6), (400, 12, 13), (300, 20, 21)]
    def st(al, k, sp=True):
        kk = dict(L=[12, 14], N=5, b=1.0, E=32000, Iy=0.0144, alfa=al, k_pod=k)
        if sp:
            kk.update(spara=True, b_s=0.3, Iy_s=0.003)
        m = DeskaMKP(Konstrukce(**kk), ex=0.25)
        s_ = reseni_stavu(m, nap, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3)
        return m, s_
    m0, s0 = st(90, None)
    m1, s1 = st(90, 1e12)
    m2, s2 = st(90, 2e6)
    kontrola("2D nosníky, k = 1e12 ≈ tuhá (max M)", s1.M.max(), s0.M.max(), 1e-4)
    kontrola("2D nosníky, k = 1e12 ≈ tuhá (max V)", np.abs(s1.Vp).max(), np.abs(s0.Vp).max(), 1e-3)
    kontrola("2D nosníky kolmé, k = 2000 MN/m/m: max M ≈ tuhá (±1 %)",
             s2.M.max(), s0.M.max(), 0.01)
    kontrola("2D nosníky, pružné: Σ reakcí = zatížení", s2.R.sum(), 2 * 400 + 300, 1e-6)
    ok = s2.dM < 1e-6 and s2.dV < 1e-6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] 2D nosníky, pružné: Σ pruhů = statika "
          f"(M {s2.dM:.1e} %, V {s2.dV:.1e} %)")
    # šikmé nosníky se spárou: uzlové reakce (v9: reakce = síla v pružině; vazba
    # β_s = ∂w/∂s – v8 zde vykazovala „vyhlazení“ špiček, které bylo z velké části
    # důsledkem parazitního smyku β_s = 0 při pružných podporách)
    def rmax(al, k):
        m, s_ = st(al, k)
        from bridge_load_calculator_v9.plate_fem import platky_z_naprav
        f = m.zatizeni(platky_z_naprav(nap, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.3))
        return np.abs(m.reakce_uzlu(f, m.res(f))).max(), s_
    r_t, st_t = rmax(120, None)
    r_k, st_k = rmax(120, 1e12)
    r_p, st_p = rmax(120, 2e6)
    kontrola("šikmé nosníky 120° se spárou: k = 1e12 ≈ tuhá (reakce podpory 1)",
             st_k.R[0], st_t.R[0], 1e-3)
    kontrola("šikmé nosníky 120° se spárou: k = 1e12 ≈ tuhá (max V nosníku)",
             np.abs(st_k.Vp).max(), np.abs(st_t.Vp).max(), 2e-3)
    print(f"         (informativně – max uzlová síla: tuhá {r_t:.1f} kN (bez momentových reakcí "
          f"β_s), k = 1e12 {r_k:.1f} kN, k_v 2000 {r_p:.1f} kN; u pružné podpory se moment "
          f"vazby β_s = ∂w/∂s přenáší silovými dvojicemi v uzlech)")
    kontrola("šikmé nosníky 120°, pružné: max M ≈ tuhá (±3 %)", st_p.M.max(), st_t.M.max(), 0.03)
    ok = st_p.dM < 1e-6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] šikmé nosníky 120°, pružné: Σ = statika (M {st_p.dM:.1e} %)")
    # šikmá deska
    from bridge_load_calculator_v9.plate_fem import platky_z_naprav
    def deska(k):
        m = DeskaSikmaMKP(Konstrukce(L=[12], N=1, b=8.0, E=32000, Iy=0.0, typ="deska", h=0.5,
                                     alfa=120, k_pod=k), ex=0.5)
        return m, reseni_stavu(m, nap[:2], 3.0, 5.0, 0.5, 0.3)
    md0, sd0 = deska(None)
    md1, sd1 = deska(1e12)
    md2, sd2 = deska(2e6)
    kontrola("šikmá deska, k = 1e12 ≈ tuhá (max m_x)", sd1.M.max(), sd0.M.max(), 1e-3)
    f2 = md2.zatizeni(platky_z_naprav(nap[:2], 3.0, 5.0, 0.5, 0.3))
    kontrola("šikmá deska, pružná: Σ reakcí = zatížení", sd2.R.sum(), f2.sum(), 1e-6)
    kontrola("šikmá deska, k = 2000 MN/m/m: max m_x ≈ tuhá (±5 %)",
             sd2.M.max(), sd0.M.max(), 0.05)


def test_smyk_kappa():
    print("\n10) Smyková tuhost Mindlinovy desky κ = 5/6 (Timošenkův nosník)")
    from bridge_load_calculator_v9.slab_fem import DeskaSikmaMKP
    from bridge_load_calculator_v9.plate_fem import KAPPA
    kontrola("κ = 5/6", KAPPA, 5.0 / 6.0, 1e-12)
    L, B, h, E, q = 6.0, 2.0, 1.0, 30000.0, 10.0       # tlustá deska L/h = 6 → smyk znatelný
    m = DeskaSikmaMKP(Konstrukce(L=[L], N=1, b=B, E=E, Iy=0.0, typ="deska", h=h, nu=0.0),
                      ex=0.0625)
    u = m.res(m.zatizeni([(q * L * B, 0.0, L, 0.0, B)]))
    k = int(np.argmin(np.abs(m.xs - L / 2)))
    w = float(np.mean(u[np.arange(m._ng) * m.nx + k]))
    Ek = E * 1000.0
    EI, GA = Ek * B * h ** 3 / 12, KAPPA * Ek / 2 * B * h
    w_b, w_s = 5 * q * B * L ** 4 / (384 * EI), q * B * L ** 2 / (8 * GA)
    kontrola(f"průhyb uprostřed = ohyb + smyk (smyk {100 * w_s / (w_b + w_s):.0f} %)",
             w, w_b + w_s, 0.01)


def test_sit():
    print("\n11) Síť MKP pro vykreslení")
    for kw, A in ((dict(N=5, E=32000, Iy=0.0144, b=1.0, alfa=110, spara=True, b_s=0.3,
                        Iy_s=0.003), (5 * 1.0 + 4 * 0.3) * 12.0),
                  (dict(N=1, beton="C30/37", b=8.0, typ_konstrukce="deska", h=0.5, alfa=120),
                   8.0 * 12.0)):
        cr = porovnani_zatizeni(typ="k", MLC="MLC40", L=[12], n=5, dist=30.5, Ve=40, d=0.4,
                                ex=0.5, obalky=False, tisk=False, k_pod=2e6, **kw)
        S = cr.sit
        x, y = S.X[S.prvky], S.Y[S.prvky]
        plocha = 0.5 * np.abs(np.sum(x * np.roll(y, -1, 1) - np.roll(x, -1, 1) * y, axis=1))
        kontrola(f"síť {'desky' if cr.K.je_deska else 'nosníků'}: Σ ploch prvků = plocha "
                 f"konstrukce", plocha.sum(), A, 1e-9)
        ok = S.k_uzlu is not None and len(S.podpory) == len(S.k_uzlu) and len(S.podpory) > 0
        vysledky.append(ok)
        print(f"[{OK if ok else FAIL}]   {len(S.prvky)} prvků, {len(S.podpory)} podepřených uzlů"
              f", {len(S.klouby)} kloubů")
    try:
        import matplotlib; matplotlib.use("Agg")
        from bridge_load_calculator_v9.plotting import plot_sit
        plot_sit(cr, show=False)
        ok = True
    except Exception as exc:
        ok = False; print("   ", exc)
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] plot_sit proběhne")


def test_okrajove_podminky():
    print("\n12) v9: okrajové podmínky podpor (tvrdé / měkké / vetknutí / pružné vetknutí)")
    from bridge_load_calculator_v9.plate_fem import DeskaMKP, reseni_stavu, platky_z_naprav
    from bridge_load_calculator_v9.slab_fem import DeskaSikmaMKP
    L, q = 12.0, 10.0
    # --- 1D
    K = Konstrukce(L=[L], N=15, b=1.0, E=32000, Iy=0.0144, uloz="vetknuti")
    nos = Nosnik1D(K)
    M, Vn, Vr, R = nos.stav([(q, 0.0, L)])
    kontrola("1D oboustranně vetknutý: M v podpoře −qL²/12", M[nos.i_sup[0]], -q * L * L / 12, 1e-3)
    kontrola("1D oboustranně vetknutý: M uprostřed qL²/24", M.max(), q * L * L / 24, 1e-3)
    kr = 1000.0
    K = Konstrukce(L=[L], N=15, b=1.0, E=32000, Iy=0.0144, uloz="vetknuti", k_rot=kr)
    nos = Nosnik1D(K)
    M, Vn, Vr, R = nos.stav([(q, 0.0, L)])
    EI = K.EI_celk
    kontrola("1D pružné vetknutí: M = −qL²/12 / (1 + 2EI/(k·B·L))", M[nos.i_sup[0]],
             -q * L * L / 12 / (1 + 2 * EI / (kr * K.B * L)), 1e-3)
    K = Konstrukce(L=[L, L], N=15, b=1.0, E=32000, Iy=0.0144, uloz="vetknuti")
    nos = Nosnik1D(K)
    M, Vn, Vr, R = nos.stav([(q, 0.0, L)])
    kontrola("1D 2 pole vetknutá, zatížené 1. pole: M nad podporou 2 = −qL²/12",
             M[nos.i_sup[1]], -q * L * L / 12, 1e-3)
    ids = [r.id for r in K.kontrolni_rezy() if r.typ == "M-"]
    ok = ids == ["M- podpora 1", "M- podpora 2", "M- podpora 3"]
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] vetknutí: řezy M- i nad krajními podporami {ids}")
    for kr_, nm, ref in ((1e14, "≈ dokonalé", "vetknuti"), (1e-6, "≈ kloub", "tvrde")):
        a = Nosnik1D(Konstrukce(L=[L, 9], N=15, b=1.0, E=32000, Iy=0.0144, uloz="vetknuti",
                                k_rot=kr_)).stav([(q, 2.0, 15.0)])[0]
        b = Nosnik1D(Konstrukce(L=[L, 9], N=15, b=1.0, E=32000, Iy=0.0144,
                                uloz=ref)).stav([(q, 2.0, 15.0)])[0]
        kontrola(f"1D pružné vetknutí k_rot → {nm} (max |M|)", np.abs(a).max(), np.abs(b).max(), 1e-4)
    # --- 2D nosníky (kolmé, 2 pole, bez spáry a se spárou)
    # Se spárou je tolerance 1 %: spára vlastní podporu nemá (vetknuty / pružně
    # uloženy jsou jen nosníky, k_v a k_rot na délku N·b), kdežto 1D model vetkne
    # celý průřez včetně Iy spár → 2D nad krajní podporou o ~0,3–0,6 % menší |M|.
    nap = [(400 / 0.5, 3.0, 3.5), (400 / 0.5, 7.0, 7.5), (300 / 0.5, 15.0, 15.5)]
    for sp_ in (False, True):
        tol_ = 1e-2 if sp_ else 5e-3
        ext_ = dict(spara=True, b_s=0.3, Iy_s=0.003) if sp_ else {}
        for uloz, kr_, kv in (("vetknuti", None, None), ("vetknuti", 5e5, None),
                              ("vetknuti", None, 2e6), ("mekke", None, None)):
            K = Konstrukce(L=[12, 10], N=5, b=1.0, E=32000, Iy=0.0144, uloz=uloz, k_rot=kr_,
                           k_pod=kv, **ext_)
            m = DeskaMKP(K, ex=0.25)
            s_ = reseni_stavu(m, nap, 0.5 * m.B - 1.0, 0.5 * m.B + 1.0, 0.5, 0.0)
            nos = Nosnik1D(K)
            M1, _, _, R1 = nos.stav(nap)
            sM = s_.P_M.sum(axis=0)
            nm = (f"{'se spárou' if sp_ else 'bez spáry'} {uloz}"
                  f"{'' if kr_ is None else ' k_rot'}{'' if kv is None else ' k_v'}")
            kontrola(f"2D nosníky {nm}: Σ M nad podporou 2 = 1D", sM[m.p_sup[0, 1]],
                     M1[nos.i_sup[1]], tol_)
            if K.vetknuti:
                kontrola(f"2D nosníky {nm}: Σ M nad podporou 1 = 1D", sM[m.p_sup[0, 0]],
                         M1[nos.i_sup[0]], tol_)
            kontrola(f"2D nosníky {nm}: reakce podpory 1 = 1D", s_.R[0], R1[0], tol_)
            ok = s_.dM < 1e-6 and s_.dV < 1e-6
            vysledky.append(ok)
            print(f"[{OK if ok else FAIL}] 2D nosníky {nm}: Σ pruhů = statika "
                  f"(M {s_.dM:.1e} %, V {s_.dV:.1e} %)")
    # --- 2D deska kolmá vetknutá (pás přes celou šířku → nosník)
    pl = [(1200.0, 3.0, 9.0, 0.0, 8.0)]
    K = Konstrukce(L=[12, 10], N=1, b=8.0, E=32000, Iy=0, typ="deska", h=0.5, uloz="vetknuti")
    m = DeskaSikmaMKP(K, ex=0.25)
    u = m.res(m.zatizeni(pl))
    sM = m.vyslednice(u)[0].sum(axis=0)
    M1 = Nosnik1D(K).stav([(200.0, 3.0, 9.0)])[0]
    kontrola("2D deska kolmá vetknutá: Σ M nad podporou 1 = 1D (±1 %)", sM[m.k_sup[0]],
             M1[0], 0.01)
    kontrola("2D deska kolmá vetknutá: Σ M max v poli = 1D (±1,5 %)", sM.max(), M1.max(), 0.015)
    # --- šikmá deska 105°: konzistentní β_s = ∂w/∂s → V u tupého rohu plynule k tuhé
    def V_roh(k, uloz="tvrde"):
        K = Konstrukce(L=[20], N=1, b=10.0, E=34000, Iy=0, typ="deska", h=0.5, alfa=105,
                       k_pod=k, uloz=uloz)
        m = DeskaSikmaMKP(K, ex=0.25)
        f = m.zatizeni([(600.0, 0.4 + K.x0(1.5), 1.4 + K.x0(1.5), 0.6, 2.4)])
        _, Vm, Vp = m.vyslednice(m.res(f))
        Vs = 0.5 * (Vm + Vp)
        return float(np.abs(Vs[:4].sum(axis=0)).max())     # pás y = 0 … 1 m
    v0, v1, v2 = V_roh(None), V_roh(1e8), V_roh(2e6)
    kontrola("šikmá deska 105°, tvrdé: V u tupého rohu, k_v = 1e5 MN/m/m ≈ tuhá", v1, v0, 5e-3)
    kontrola("šikmá deska 105°, tvrdé: V u tupého rohu, k_v = 2000 vs tuhá (±5 %, v8 +30 %)",
             v2, v0, 0.05)
    vm = V_roh(None, "mekke")
    ok = abs(vm - v0) > 1e-6
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] šikmá deska: měkké uložení mění V u rohu ({v0:.1f} → {vm:.1f})")
    # --- celý výpočet
    cr = porovnani_zatizeni(typ="k", MLC="MLC40", L=[12, 12], n=5, dist=30.5, Ve=40, N=1,
                            beton="C30/37", b=8.0, d=0.4, typ_konstrukce="deska", h=0.5,
                            alfa=110, uloz="vetknuti", k_rot=5e5, k_pod=2e6, ex=0.5,
                            obalky=True, krok_obalky=1.0, tisk=False)
    ids = [r.rez.id for r in cr.rezy]
    ok = "M- podpora 1" in ids and "M- podpora 3" in ids and cr.ob_MLC.M_min.min() < 0
    vysledky.append(ok)
    print(f"[{OK if ok else FAIL}] porovnani_zatizeni(uloz='vetknuti'): řezy {ids[:5]}…, "
          f"obálka M_min {cr.ob_MLC.M_min.min():.1f}")
    # --- regrese v8 (tvrdé, tuhé): nosníky shodně; deska M+ a V shodně
    try:
        import bridge_load_calculator_v8 as v8
    except ImportError:
        print("   (balíček v8 není v cestě — regrese přeskočena)")
        return
    for kw in (dict(N=5, Iy=0.0144, b=1.0, E=32000, alfa=110, spara=True, b_s=0.3, Iy_s=0.003),
               dict(N=1, b=8.0, E=32000, typ_konstrukce="deska", h=0.5, alfa=110)):
        base = dict(typ="k", MLC="MLC80", L=[12, 14], n=10, dist=30.5, Ve=80, d=0.5, ex=0.25,
                    obalky=False, tisk=False)
        a = v8.porovnani_zatizeni(**base, **kw)
        b = porovnani_zatizeni(**base, **kw)
        deska_ = kw.get("typ_konstrukce") == "deska"
        d_ = max(max(abs(ra.MLC_2D - rb.MLC_2D), abs(ra.Ve_2D - rb.Ve_2D))
                 for ra, rb in zip(a.rezy, b.rezy) if not (deska_ and ra.rez.typ == "M-"))
        kontrola(f"v9 = v8 ({'deska M+, V' if deska_ else 'šikmé nosníky, všechny řezy'}), "
                 f"max rozdíl", 1.0 + d_, 1.0, 1e-6)
        a2 = v8.porovnani_zatizeni(**base, **kw, k_pod=2e6)
        b2 = porovnani_zatizeni(**base, **kw, k_pod=2e6, beta_s_pevne=True)
        d2 = max(max(abs(ra.MLC_2D - rb.MLC_2D), abs(ra.Ve_2D - rb.Ve_2D))
                 for ra, rb in zip(a2.rezy, b2.rezy) if not (deska_ and ra.rez.typ == "M-"))
        kontrola(f"v9 (β_s = 0, k_v 2000) = v8 (k_v 2000), {'deska' if deska_ else 'nosníky'}",
                 1.0 + d2, 1.0, 1e-6)
        if deska_:
            for ra, rb in zip(a.rezy, b.rezy):
                if ra.rez.typ == "M-":
                    print(f"         (deska {ra.rez.id}: v8 {ra.MLC_2D:.1f} → v9 {rb.MLC_2D:.1f} "
                          f"kNm/m – extrapolace m_x nad podporou)")


if __name__ == "__main__":
    test_analytika_dve_pole()
    test_analytika_tri_pole()
    test_regrese_v5()
    test_rovnovaha_deska()
    test_tri_pole_zona_obalky()
    test_V_v_rezu_d()
    test_spara()
    test_v8()
    test_pruzna_podpora()
    test_smyk_kappa()
    test_sit()
    test_okrajove_podminky()
    print(f"\nVýsledek: {sum(vysledky)}/{len(vysledky)} kontrol v pořádku.")
    sys.exit(0 if all(vysledky) else 1)
