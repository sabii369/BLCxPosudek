"""Obecný betonový průřez zadaný numericky (polygon / lichoběžníkové vrstvy).

Souřadnice: y – vodorovně [mm], z – svisle od spodního okraje průřezu [mm].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _polygon_charakteristiky(pts: np.ndarray) -> tuple[float, float, float]:
    """Plocha, statický moment k z=0 a moment setrvačnosti k z=0 (absolutní hodnoty)."""
    y = pts[:, 0]
    z = pts[:, 1]
    y1, z1 = np.roll(y, -1), np.roll(z, -1)
    cross = y * z1 - y1 * z
    A = 0.5 * cross.sum()
    Sy = (z + z1) * cross
    Sy = Sy.sum() / 6.0
    Iy = ((z * z + z * z1 + z1 * z1) * cross).sum() / 12.0
    if A < 0:
        A, Sy, Iy = -A, -Sy, -Iy
    return A, Sy, Iy


def _obvod(pts: np.ndarray) -> float:
    d = np.diff(np.vstack([pts, pts[:1]]), axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def _sirka_polygonu(pts: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Šířka (součet délek průsečíků) polygonu s vodorovnými přímkami z."""
    z = np.atleast_1d(np.asarray(z, dtype=float))
    y0, z0 = pts[:, 0], pts[:, 1]
    y1, z1 = np.roll(y0, -1), np.roll(z0, -1)
    out = np.zeros_like(z)
    for i, zz in enumerate(z):
        cond = ((z0 <= zz) & (z1 > zz)) | ((z1 <= zz) & (z0 > zz))
        if not cond.any():
            continue
        t = (zz - z0[cond]) / (z1[cond] - z0[cond])
        ys = np.sort(y0[cond] + t * (y1[cond] - y0[cond]))
        out[i] = (ys[1::2] - ys[0::2]).sum()
    return out


@dataclass
class Prurez:
    """Betonový průřez zadaný obrysovým polygonem a případnými otvory."""

    obrys: np.ndarray
    otvory: list[np.ndarray] = field(default_factory=list)
    nazev: str = ""
    obvod_vysychani: float | None = None  # mm, pro h0
    n_pasu: int = 600

    def __post_init__(self):
        self.obrys = np.asarray(self.obrys, dtype=float)
        self.otvory = [np.asarray(o, dtype=float) for o in self.otvory]
        zmin = self.obrys[:, 1].min()
        if abs(zmin) > 1e-9:  # posun tak, aby spodní okraj byl z = 0
            self.obrys[:, 1] -= zmin
            for o in self.otvory:
                o[:, 1] -= zmin
        A, S, I0 = _polygon_charakteristiky(self.obrys)
        for o in self.otvory:
            a, s, i0 = _polygon_charakteristiky(o)
            A, S, I0 = A - a, S - s, I0 - i0
        self.A = A
        self.zt = S / A
        self.I = I0 - A * self.zt ** 2
        self.h = float(self.obrys[:, 1].max())
        self.b_max = float(np.ptp(self.obrys[:, 0]))
        self.obvod = _obvod(self.obrys) + sum(_obvod(o) for o in self.otvory)
        # jemné pásy pro integraci (MSÚ, statické momenty)
        dz = self.h / self.n_pasu
        self._zp = (np.arange(self.n_pasu) + 0.5) * dz
        self._dz = dz
        self._bp = self.sirka(self._zp)

    # ------------------------------------------------------------------
    @classmethod
    def obdelnik(cls, b: float, h: float, **kw) -> "Prurez":
        return cls(np.array([[-b / 2, 0], [b / 2, 0], [b / 2, h], [-b / 2, h]]), **kw)

    @classmethod
    def z_vrstev(cls, vrstvy: list[tuple[float, float, float]], **kw) -> "Prurez":
        """Symetrický průřez z lichoběžníkových vrstev zadaných odspodu.

        vrstvy: [(b_dolni, b_horni, vyska), ...] v mm
        """
        z = 0.0
        prava, leva = [], []
        for bd, bh, hv in vrstvy:
            prava += [(bd / 2, z), (bh / 2, z + hv)]
            leva += [(-bd / 2, z), (-bh / 2, z + hv)]
            z += hv
        pts = prava + leva[::-1]
        # odstranění duplicitních sousedních bodů
        clean = [pts[0]]
        for p in pts[1:]:
            if np.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-9:
                clean.append(p)
        if np.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) < 1e-9:
            clean.pop()
        return cls(np.array(clean), **kw)

    # ------------------------------------------------------------------
    def sirka(self, z) -> np.ndarray:
        b = _sirka_polygonu(self.obrys, z)
        for o in self.otvory:
            b = b - _sirka_polygonu(o, z)
        return b

    @property
    def W_h(self) -> float:
        return self.I / (self.h - self.zt)

    @property
    def W_d(self) -> float:
        return self.I / self.zt

    @property
    def u(self) -> float:
        return self.obvod_vysychani if self.obvod_vysychani else self.obvod

    @property
    def h0(self) -> float:
        """Náhradní rozměr h0 = 2·Ac/u [mm]."""
        return 2.0 * self.A / self.u

    def pasy(self):
        """(z středů pásů, tloušťka, šířka) pro numerickou integraci."""
        return self._zp, self._dz, self._bp

    def staticky_moment(self, z) -> np.ndarray:
        """Statický moment části průřezu nad úrovní z k těžišti [mm3]."""
        z = np.atleast_1d(np.asarray(z, dtype=float))
        zp, dz, bp = self.pasy()
        contrib = bp * dz * (zp - self.zt)
        cum_above = np.cumsum(contrib[::-1])[::-1]  # součet od pásu i nahoru
        # interpolace na hranice pásů
        edges = np.concatenate([zp - dz / 2, [self.h]])
        vals = np.concatenate([cum_above, [0.0]])
        return np.interp(z, edges, vals)

    def charakteristiky_s_body(self, body: list[tuple[float, float]]) -> tuple[float, float, float]:
        """Průřezové charakteristiky s přidanými/odebranými bodovými plochami.

        body: [(z, ΔA), ...] – kladné ΔA = přidaná (ideální) plocha, záporné = otvor.
        Vrací (A, z_t, I).
        """
        A = self.A
        S = self.A * self.zt
        I0 = self.I + self.A * self.zt ** 2
        for z, dA in body:
            A += dA
            S += dA * z
            I0 += dA * z * z
        zt = S / A
        return A, zt, I0 - A * zt * zt
