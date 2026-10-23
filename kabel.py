"""Geometrie předpínacích kabelů / lan po délce nosníku.

Délky po nosníku x [m] (0 = levý konec nosníku), polohy kabelu z [mm] od spodního
okraje průřezu. Geometrie se diskretizuje jemným vzorkováním; z něj se určí
sklon α(x), délka kabelu s(x) a součet úhlových změn θ(x) pro výpočet ztrát třením.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .materialy import PredpinaciVyztuz


@dataclass
class GeometrieKabelu:
    """Diskretizovaná geometrie kabelu."""

    x: np.ndarray      # m
    z: np.ndarray      # mm
    alfa: np.ndarray   # rad, sklon (kladný = stoupá doprava)
    s: np.ndarray      # m, délka kabelu od levé kotvy
    theta: np.ndarray  # rad, součet absolutních úhlových změn od levé kotvy

    def z_v(self, x) -> np.ndarray:
        return np.interp(x, self.x, self.z)

    def alfa_v(self, x) -> np.ndarray:
        return np.interp(x, self.x, self.alfa)


def _geometrie_z_bodu(x: np.ndarray, z_m: np.ndarray) -> GeometrieKabelu:
    """Z hustě vzorkovaných bodů (x v m, z v m) sestaví geometrii (lomená čára)."""
    dx = np.diff(x)
    dz = np.diff(z_m)
    seg_a = np.arctan2(dz, dx)
    seg_l = np.hypot(dx, dz)
    s = np.concatenate([[0.0], np.cumsum(seg_l)])
    dtheta = np.abs(np.diff(seg_a))
    theta = np.concatenate([[0.0, 0.0], np.cumsum(dtheta)])
    # sklon v uzlech – průměr sousedních úseků
    a = np.empty_like(x)
    a[0], a[-1] = seg_a[0], seg_a[-1]
    a[1:-1] = 0.5 * (seg_a[:-1] + seg_a[1:])
    return GeometrieKabelu(x=x, z=z_m * 1000.0, alfa=a, s=s, theta=theta)


def geometrie_parabola(L: float, z_L: float, z_S: float, z_P: float,
                       x_S: float | None = None, n: int = 2001) -> GeometrieKabelu:
    """Dvě paraboly s vrcholem (vodorovnou tečnou) v bodě x_S."""
    x_S = L / 2 if x_S is None else x_S
    x = np.linspace(0.0, L, n)
    x = np.union1d(x, [x_S])
    z = np.where(
        x <= x_S,
        z_S + (z_L - z_S) * ((x_S - x) / x_S) ** 2,
        z_S + (z_P - z_S) * ((x - x_S) / (L - x_S)) ** 2,
    )
    return _geometrie_z_bodu(x, z / 1000.0)


def geometrie_polygon(body: list[tuple[float, float]], polomery: list[float] | None = None,
                      krok: float = 0.005) -> GeometrieKabelu:
    """Lomená čára přes body [(x [m], z [mm])], ve vnitřních bodech volitelně
    zaoblená kružnicovým obloukem poloměru R [m] (0 = ostrý lom)."""
    P = np.array([(bx, bz / 1000.0) for bx, bz in body], dtype=float)
    nb = len(P)
    R = np.zeros(nb) if polomery is None else np.asarray(list(polomery) + [0] * nb, float)[:nb]
    pts: list[tuple[float, float]] = [tuple(P[0])]
    for i in range(1, nb - 1):
        if R[i] <= 0:
            pts.append(tuple(P[i]))
            continue
        d1 = P[i] - P[i - 1]
        d2 = P[i + 1] - P[i]
        d1 /= np.linalg.norm(d1)
        d2 /= np.linalg.norm(d2)
        dev = np.arccos(np.clip(d1 @ d2, -1, 1))
        if dev < 1e-9:
            pts.append(tuple(P[i]))
            continue
        T = R[i] * np.tan(dev / 2)
        A = P[i] - T * d1
        B = P[i] + T * d2
        # střed oblouku
        nrm = np.array([-d1[1], d1[0]])
        if d1[0] * d2[1] - d1[1] * d2[0] < 0:
            nrm = -nrm
        C = A + R[i] * nrm
        a0 = np.arctan2(*(A - C)[::-1])
        a1 = np.arctan2(*(B - C)[::-1])
        da = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
        m = max(int(abs(da) * R[i] / krok), 8)
        for t in np.linspace(0, 1, m + 1):
            ang = a0 + da * t
            pts.append((C[0] + R[i] * np.cos(ang), C[1] + R[i] * np.sin(ang)))
    pts.append(tuple(P[-1]))
    pts_a = np.array(pts)
    # doplnění rovných úseků jemným vzorkováním
    xs, zs = [pts_a[0, 0]], [pts_a[0, 1]]
    for (xa, za), (xb, zb) in zip(pts_a[:-1], pts_a[1:]):
        m = max(int(np.hypot(xb - xa, zb - za) / krok), 1)
        t = np.linspace(0, 1, m + 1)[1:]
        xs += list(xa + (xb - xa) * t)
        zs += list(za + (zb - za) * t)
    xs, zs = np.array(xs), np.array(zs)
    keep = np.concatenate([[True], np.diff(xs) > 1e-12])
    return _geometrie_z_bodu(xs[keep], zs[keep])


def geometrie_primka(L: float, z_L: float, z_P: float | None = None) -> GeometrieKabelu:
    z_P = z_L if z_P is None else z_P
    return geometrie_polygon([(0.0, z_L), (L, z_P)], krok=L / 200)


@dataclass
class Kabel:
    """Předpínací kabel (dodatečně předpjatý) nebo skupina lan (předem předpjatá)."""

    nazev: str
    pocet_lan: int
    vyztuz: PredpinaciVyztuz
    geometrie: GeometrieKabelu
    sigma_max: float               # napínací napětí na lisu [MPa]
    napinani: str = "levy"         # levy | pravy | oba
    mu: float = 0.19               # součinitel tření
    k: float = 0.005               # neúmyslná úhlová změna [rad/m]
    pokluz: float = 6.0            # pokluz v kotvě [mm]
    d_kanalku: float = 0.0         # vnější průměr kabelového kanálku [mm]
    poradi_napinani: int = 1       # pořadí při postupném napínání
    popis_geometrie: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def Ap(self) -> float:
        return self.pocet_lan * self.vyztuz.Ap_lano

    @property
    def P_max(self) -> float:
        """Síla na lisu [kN]."""
        return self.sigma_max * self.Ap / 1000.0
