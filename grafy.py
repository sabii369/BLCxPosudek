"""Grafické výstupy posudku (matplotlib → PNG)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402

# kategorická paleta (pevné pořadí) a stavové barvy
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OK = "#0ca30c"
WARN = "#fab219"
BAD = "#d03b3b"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#d9d8d4"
SURF = "#fcfcfb"
LIMIT = "#52514e"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "legend.frameon": False, "lines.linewidth": 2.0, "figure.dpi": 110,
})


def _uloz(fig, adr: Path, nazev: str) -> str:
    p = adr / f"{nazev}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p.name


def _limit(ax, y, text, x=None, color=LIMIT):
    ax.axhline(y, color=color, lw=1.2, ls="--")
    xl = ax.get_xlim()
    ax.text(xl[1] if x is None else x, y, " " + text, va="bottom", ha="right", color=color, fontsize=8)


def diagramy_materialu(m, adr):
    b, p, s = m.beton, m.predp, m.betonarska
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.2))
    e = np.linspace(0, b.eps_cu2, 200)
    ax[0].plot(e * 1e3, -b.sigma_msu(-e), color=C[0])
    ax[0].set(title=f"Beton {b.trida} – parabola-obdélník", xlabel="ε_c [‰]", ylabel="σ_c [MPa]")
    ep = np.linspace(0, p.eps_ud, 200)
    ax[1].plot(ep * 1e3, p.sigma_msu(ep), color=C[1])
    ax[1].set(title=f"Předpínací výztuž {p.typ}", xlabel="ε_p [‰]", ylabel="σ_p [MPa]")
    es = np.linspace(0, s.eps_ud, 200)
    ax[2].plot(es * 1e3, s.sigma_msu(es), color=C[2])
    ax[2].set(title=f"Betonářská výztuž {s.typ}", xlabel="ε_s [‰]", ylabel="σ_s [MPa]")
    return _uloz(fig, adr, "diagramy_materialu")


def prurez(m, adr):
    P = m.prurez
    fig, axs = plt.subplots(1, 2, figsize=(9, 4.6), sharey=True)
    for ax, i, nazev in ((axs[0], m.im, "střed rozpětí"), (axs[1], m.ia, "nad ložiskem")):
        ax.add_patch(Polygon(P.obrys, closed=True, fc="#e9eef6", ec=INK2, lw=1.2))
        for o in P.otvory:
            ax.add_patch(Polygon(o, closed=True, fc=SURF, ec=INK2, lw=1.0))
        ax.axhline(P.zt, color=INK2, lw=0.8, ls="-.")
        ax.text(P.obrys[:, 0].max(), P.zt, f"  T (z_t = {P.zt:.0f})", va="center", color=INK2, fontsize=8)
        for j, (k, z) in enumerate(zip(m.kabely, m.zk)):
            r = max(k.d_kanalku / 2, 15)
            ax.add_patch(Circle((0 + (j - (len(m.kabely) - 1) / 2) * 2.2 * r * 0, z[i]), r, fc=C[j % 8],
                                ec="white", lw=1.5, alpha=0.9))
            ax.text(r * 1.3, z[i], f" {k.nazev} z={z[i]:.0f}", va="center", fontsize=8, color=INK)
        for v in m.vyztuz:
            w = P.sirka(v.z)[0]
            ax.plot([-w / 2 + 40, w / 2 - 40], [v.z, v.z], color=INK, lw=2.5)
        ax.set_aspect("equal")
        ax.set_xlim(P.obrys[:, 0].min() - 80, P.obrys[:, 0].max() + 350)
        ax.set_ylim(-60, P.h + 60)
        ax.set_title(f"Příčný řez – {nazev}")
        ax.set_xlabel("y [mm]")
    axs[0].set_ylabel("z [mm]")
    return _uloz(fig, adr, "prurez")


def kabely(m, adr):
    fig, ax = plt.subplots(figsize=(11, 3.4))
    P = m.prurez
    ax.fill_between([0, m.L], 0, P.h, color="#e9eef6", lw=0)
    ax.axhline(P.zt, color=INK2, lw=0.8, ls="-.")
    for j, (k, z) in enumerate(zip(m.kabely, m.zk)):
        ax.plot(k.geometrie.x, k.geometrie.z, color=C[j % 8], label=k.nazev)
    for xs in (m.xa, m.xb):
        ax.plot([xs], [-0.04 * P.h], marker="^", ms=10, color=INK2)
    ax.set(xlabel="x [m]", ylabel="z [mm]", title="Vedení kabelů", xlim=(-0.2, m.L + 0.2), ylim=(-0.1 * P.h, 1.05 * P.h))
    ax.legend(loc="upper center", ncol=len(m.kabely))
    return _uloz(fig, adr, "kabely")


def napeti_kabelu(m, adr):
    n = len(m.kabely)
    fig, axs = plt.subplots(n, 1, figsize=(11, 2.8 * n), squeeze=False)
    for j, k in enumerate(m.kabely):
        ax = axs[j, 0]
        if not m.predem:
            ax.plot(m.x, m.sig_tr[j], color=C[0], label="po tření")
        ax.plot(m.x, m.sig_pokl[j], color=C[1], label="po pokluzu" if not m.predem else "před uvolněním")
        ax.plot(m.x, m.sig_pm0[j], color=C[2], label="po pružném přetvoření σ_pm0")
        for i, f in enumerate(m.faze[1:]):
            ax.plot(m.x, f.sigma[j], color=C[3 + i % 5], lw=1.5, label=f"t = {f.t:.0f} d")
        _limit(ax, m.lim_pm0, "σ_pm0,max")
        ax.set(title=f"Kabel {k.nazev}", xlabel="x [m]", ylabel="σ_p [MPa]")
        ax.legend(ncol=4, fontsize=8, loc="lower center")
    return _uloz(fig, adr, "napeti_kabelu")


def ztraty_rozklad(m, adr):
    im = m.im
    f = m.faze[-1]
    labels, vals = [], []
    for j, k in enumerate(m.kabely):
        d = f.ztraty["kabely"][j]
        smax = k.sigma_max
        tr = smax - m.sig_tr[j][im]
        pk = m.sig_tr[j][im] - m.sig_pokl[j][im]
        el = m.d_el[j][im]
        mez = d["mezi"]
        jm = mez["jmenovatel"][im]
        cs = mez["clen_smrst"] / jm
        rel = mez["clen_relax"][im] / jm
        cr = mez["clen_dotv"][im] / jm
        labels.append(k.nazev)
        vals.append([tr, pk, el, cs, cr, rel])
    vals = np.array(vals)
    names = ["tření" if not m.predem else "–", "pokluz" if not m.predem else "relaxace před uvolněním",
             "pružné přetvoření", "smršťování", "dotvarování", "relaxace"]
    fig, ax = plt.subplots(figsize=(9, 0.9 + 0.7 * len(labels) + 0.6))
    left = np.zeros(len(labels))
    for i in range(vals.shape[1]):
        if np.allclose(vals[:, i], 0):
            continue
        ax.barh(labels, vals[:, i], left=left, color=C[i], edgecolor=SURF, linewidth=2, height=0.55,
                label=names[i])
        for y, (l0, v) in enumerate(zip(left, vals[:, i])):
            if v > 0.06 * vals.sum(1).max():
                ax.text(l0 + v / 2, y, f"{v:.0f}", ha="center", va="center", color="white", fontsize=8)
        left += vals[:, i]
    for y, tot in enumerate(left):
        ax.text(tot, y, f"  Σ {tot:.0f} MPa ({100 * tot / m.kabely[y].sigma_max:.1f} %)", va="center",
                color=INK, fontsize=8)
    ax.set(xlabel="ztráta napětí Δσ_p [MPa]", title=f"Rozklad ztrát ve středu rozpětí – konec životnosti")
    ax.set_xlim(0, left.max() * 1.3)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.35), fontsize=8)
    ax.grid(axis="y", visible=False)
    return _uloz(fig, adr, "ztraty_rozklad")


def sila_v_case(m, adr):
    im = m.im
    ts = np.unique(np.concatenate([np.geomspace(m.t0 + 0.01, m.t_konec, 70), [f.t for f in m.faze]]))
    P = []
    for t in ts:
        sigs = m._dlouhodobe(t)[0]
        P.append(-m._sily_predpeti(sigs)[0][im])
    P0 = -m._sily_predpeti(m.sig_pm0)[0][im]
    Pmax = sum(k.P_max for k in m.kabely)
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.semilogx(np.concatenate([[m.t0], ts]), np.concatenate([[P0], P]), color=C[0])
    ax.axhline(Pmax, color=LIMIT, lw=1, ls="--")
    ax.text(ts[0], Pmax, " P_max (na lisu)", va="bottom", fontsize=8, color=LIMIT)
    for j, f in enumerate(m.faze):
        Pf = -m._sily_predpeti(f.sigma)[0][im]
        ax.plot([f.t], [Pf], "o", ms=8, color=C[1], mec=SURF, mew=2)
        dy = 10 if j % 2 == 0 else -26
        ax.annotate(f"{f.nazev}\n{Pf:.0f} kN", (f.t, Pf), textcoords="offset points", xytext=(5, dy), fontsize=7,
                    color=INK2)
    ax.set(xlabel="stáří betonu t [dny] (log)", ylabel="P_m,t [kN]", title="Předpínací síla ve středu rozpětí")
    return _uloz(fig, adr, "sila_v_case")


def vnitrni_sily(m, adr):
    f = m.faze[-1]
    d = m.komb[f.nazev]
    NP, MP, VP = m._sily_predpeti(f.sigma)
    fig, axs = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True)
    ax = axs[0]
    ax.plot(m.x, m.zs_g0.M_max, color=C[0], label="g0")
    ax.plot(m.x, d["vse_char"].M_max, color=C[1], label="charakteristická")
    ax.plot(m.x, d["msu"].M_max, color=C[2], label="MSÚ (M_Ed)")
    ax.plot(m.x, MP, color=C[6], label="předpětí M_P,∞")
    ax.invert_yaxis()
    ax.set(ylabel="M [kNm]", title="Ohybové momenty (kladné dolů)")
    ax.legend(ncol=4)
    ax = axs[1]
    ax.plot(m.x, d["msu"].V_max, color=C[2], label="MSÚ V_Ed,max")
    ax.plot(m.x, d["msu"].V_min, color=C[2], lw=1.2, ls="--", label="MSÚ V_Ed,min")
    ax.plot(m.x, VP, color=C[6], label="předpětí V_P,∞")
    ax.set(xlabel="x [m]", ylabel="V [kN]", title="Posouvající síly")
    ax.legend(ncol=3)
    return _uloz(fig, adr, "vnitrni_sily")


def napeti_faze(m, adr):
    out = []
    from .zatizeni import NAZVY_KOMBINACI
    b, nn = m.beton, m.n
    for idx, f in enumerate(m.faze):
        res = m.msp_napeti[f.nazev]
        fig, axs = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
        for ax, iv, naz in ((axs[0], 0, "horní vlákna"), (axs[1], 1, "dolní vlákna")):
            for ci, (druh, o) in enumerate(res.items()):
                lo = np.min([v[iv] for v in o.values()], 0)
                hi = np.max([v[iv] for v in o.values()], 0)
                ax.fill_between(m.x, lo, hi, color=C[ci], alpha=0.25, lw=0)
                ax.plot(m.x, lo, color=C[ci], lw=1.4, label=NAZVY_KOMBINACI[druh])
                ax.plot(m.x, hi, color=C[ci], lw=1.4)
            fck = b.fck_t(f.t)
            k_tl = nn.k_predpeti if idx == 0 else nn.k1
            ax.axhline(-k_tl * fck, color=BAD, ls="--", lw=1.2)
            ax.text(m.x[0], -k_tl * fck, f" −{k_tl}·f_ck(t)", va="bottom", fontsize=8, color=BAD)
            if f.provoz:
                ax.axhline(-nn.k2 * fck, color=WARN, ls="--", lw=1.2)
                ax.text(m.x[0], -nn.k2 * fck, f" −{nn.k2}·f_ck", va="bottom", fontsize=8, color=INK2)
            ft = m._mez_tahu(nn.tah_provoz if f.provoz else nn.tah_predpeti, f.t)
            ax.axhline(ft, color=BAD, ls="--", lw=1.2)
            ax.text(m.x[0], ft, " mez tahu", va="bottom", fontsize=8, color=BAD)
            ax.axhline(0, color=INK2, lw=0.8)
            ax.set(title=f"{naz}", xlabel="x [m]")
        axs[0].set_ylabel("σ_c [MPa] (tah +, tlak −)")
        axs[0].legend(fontsize=8, loc="lower right")
        fig.suptitle(f"Napětí v betonu – {f.nazev} (t = {f.t:.0f} d), obálka P_sup/P_inf", fontsize=10,
                     fontweight="bold", color=INK)
        out.append(_uloz(fig, adr, f"napeti_{idx}"))
    return out


def napeti_profil(m, adr):
    P = m.prurez
    i = m.im
    z = np.linspace(0, P.h, 50)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    for j, f in enumerate(m.faze):
        NP, MP, _ = m._sily_predpeti(f.sigma)
        d = m.komb[f.nazev]
        Mx = d["char"].M_max[i]
        s = m._napeti(z, NP[i], MP[i], m.zs_g0.M_max[i], Mx, idx=i)
        ax.plot(s, z, color=C[j % 8], label=f"{f.nazev} ({'char.' if f.provoz else 'stálá'})")
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set(xlabel="σ_c [MPa]", ylabel="z [mm]", title=f"Napětí po výšce – střed rozpětí (P_m,t)")
    ax.legend(fontsize=7)
    return _uloz(fig, adr, "napeti_profil")


def hlavni_napeti(m, adr):
    if not getattr(m, "hlavni", None):
        return None
    f = list(m.hlavni)[-1]
    h = m.hlavni[f]
    if h["prof"] is None:
        return None
    sx, tau, s1, s3, fctb = h["prof"]
    z = h["z"]
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))
    ax = axs[0]
    ax.plot(sx, z, color=C[0], label="σ_x")
    ax.plot(tau, z, color=C[1], label="τ")
    ax.plot(s1, z, color=C[2], label="σ_1")
    ax.plot(s3, z, color=C[6], label="σ_3")
    ax.plot(fctb, z, color=BAD, ls="--", lw=1.2, label="f_ctb")
    ax.set(xlabel="napětí [MPa]", ylabel="z [mm]", title=f"Řez x = {m.x[h['i']]:.2f} m – {f}")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.plot(h["x"], h["eta_x"], color=C[0])
    ax.axhline(1.0, color=BAD, ls="--", lw=1.2)
    ax.set(xlabel="x [m]", ylabel="σ_1/f_ctb [-]", title="Využití hlavním tahovým napětím po délce")
    return _uloz(fig, adr, "hlavni_napeti")


def pruhyb(m, adr):
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for j, (k, w) in enumerate(m.w.items()):
        ax.plot(m.w_x, w, color=C[j % 8], lw=1.6, label=k)
    lim = m.L0 * 1000 / m.n.pruhyb_limit
    ax.axhline(lim, color=BAD, ls="--", lw=1.2)
    ax.text(m.w_x[0], lim, f" L/{m.n.pruhyb_limit:.0f}", va="bottom", fontsize=8, color=BAD)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.invert_yaxis()
    ax.set(xlabel="x [m]", ylabel="w [mm] (dolů +)", title="Průhyb")
    ax.legend(fontsize=7, ncol=2)
    return _uloz(fig, adr, "pruhyb")


def msu_ohyb(m, adr):
    if not m.msu_M:
        return None
    fig, ax = plt.subplots(figsize=(10, 3.6))
    for j, (f, d) in enumerate(m.msu_M.items()):
        ax.plot(m.x, d["MRd"], color=C[j * 2 % 8], label=f"M_Rd – {f}")
    d = list(m.msu_M.values())[-1]
    ax.plot(m.x, np.where(m.v_poli, d["MEd"], np.nan), color=C[1], label="M_Ed")
    ax.set(xlabel="x [m]", ylabel="M [kNm]", title="Ohybová únosnost po délce nosníku")
    ax.legend(fontsize=8)
    return _uloz(fig, adr, "msu_ohyb")


def msu_pretvoreni(m, adr):
    if not m.msu_M:
        return None
    f, d = list(m.msu_M.items())[-1]
    r = d["vys"][d["i"]]
    P = m.prurez
    z = np.linspace(0, P.h, 200)
    zn = P.h - r.x
    eps = r.kappa * (zn - z)
    sig = -m.beton.sigma_msu(eps)
    fig, axs = plt.subplots(1, 3, figsize=(11, 4.2), sharey=True)
    ax = axs[0]
    ax.add_patch(Polygon(P.obrys, closed=True, fc="#e9eef6", ec=INK2))
    ax.axhline(zn, color=BAD, ls="--", lw=1)
    for j, v in enumerate(r.vrstvy_p):
        ax.plot([0], [v["z"]], "o", color=C[j % 8], ms=8)
    ax.set_aspect("equal")
    ax.set(title="Průřez a neutrálná osa", xlabel="y [mm]", ylabel="z [mm]")
    ax = axs[1]
    ax.plot(eps * 1e3, z, color=C[0], label="ε (rovina průřezu)")
    for j, v in enumerate(r.vrstvy_p):
        ax.plot([v["eps"] * 1e3], [v["z"]], "o", color=C[j % 8], ms=8, label=f"ε_p {v['nazev']} (vč. ε_p0)")
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set(title="Přetvoření [‰]", xlabel="ε [‰]")
    ax.legend(fontsize=7)
    ax = axs[2]
    ax.fill_betweenx(z, 0, sig, color=C[0], alpha=0.35, lw=0)
    ax.plot(sig, z, color=C[0])
    ax.set(title="Napětí v betonu [MPa]", xlabel="σ_c [MPa]")
    fig.suptitle(f"MSÚ – x = {m.x[d['i']]:.2f} m, {f}: M_Rd = {r.MRd:.0f} kNm, x = {r.x:.0f} mm, rozhoduje {r.rozhoduje}",
                 fontsize=10, fontweight="bold", color=INK)
    return _uloz(fig, adr, "msu_pretvoreni")


def msu_smyk(m, adr):
    if not m.msu_V:
        return None
    f, d = list(m.msu_V.items())[-1]
    a = d["arr"]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(m.x, a["VEd"], color=C[1], label="|V_Ed| (vč. V_P)")
    ax.plot(m.x, a["VRdc"], color=C[0], lw=1.4, label="V_Rd,c")
    ax.plot(m.x, a["VRds"], color=C[2], lw=1.4, label="V_Rd,s")
    ax.plot(m.x, a["VRdmax"], color=C[6], lw=1.4, label="V_Rd,max")
    ax.plot(m.x, a["VRd"], color=INK, lw=1.0, ls="--", label="V_Rd")
    ax.set(xlabel="x [m]", ylabel="V [kN]", title=f"Smyková únosnost – {f}")
    ax.legend(fontsize=8, ncol=5)
    return _uloz(fig, adr, "msu_smyk")


def vyuziti(m, adr):
    # nejvyšší využití pro každé kritérium přes všechny fáze
    best: dict[tuple[str, str], object] = {}
    for v in m.protokol.posudky:
        key = (v.mezni_stav, v.nazev)
        if key not in best or v.vyuziti > best[key].vyuziti:
            best[key] = v
    items = sorted(best.values(), key=lambda v: (v.mezni_stav != "MSÚ", v.skupina, v.nazev))
    fig, ax = plt.subplots(figsize=(10, 0.8 + 0.32 * len(items)))
    names = [f"{v.mezni_stav}: {v.nazev}" for v in items]
    vals = [min(v.vyuziti, 2.0) for v in items]
    cols = [OK if v.vyuziti <= 0.9 else (WARN if v.vyuziti <= 1.0 else BAD) for v in items]
    y = np.arange(len(items))[::-1]
    ax.barh(y, vals, color=cols, height=0.62, edgecolor=SURF, linewidth=2)
    for yi, v, val in zip(y, items, vals):
        ax.text(val, yi, f"  {v.vyuziti * 100:.0f} %" + (" ✔" if v.vyhovuje else " ✘ NEVYHOVUJE"),
                va="center", fontsize=8, color=INK)
    ax.set_yticks(y, names, fontsize=8)
    ax.axvline(1.0, color=BAD, ls="--", lw=1.2)
    ax.set_xlim(0, max(1.25, max(vals) * 1.25))
    ax.set(xlabel="využití η [-]", title="Souhrn využití – mezní stavy")
    ax.grid(axis="y", visible=False)
    return _uloz(fig, adr, "vyuziti")


def vykresli_vse(m, adr: str | Path) -> dict[str, str]:
    adr = Path(adr)
    adr.mkdir(parents=True, exist_ok=True)
    out = {}
    for fn in (diagramy_materialu, prurez, kabely, napeti_kabelu, ztraty_rozklad, sila_v_case, vnitrni_sily,
               napeti_profil, hlavni_napeti, pruhyb, msu_ohyb, msu_pretvoreni, msu_smyk, vyuziti):
        r = fn(m, adr)
        if r:
            out[fn.__name__] = r
    for i, r in enumerate(napeti_faze(m, adr)):
        out[f"napeti_{i}"] = r
    return out
