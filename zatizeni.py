"""Zatížení prostého nosníku (s převislými konci) a kombinace podle ČSN EN 1990.

x [m] od levého konce nosníku, síly [kN], momenty [kNm]. Kladný moment = tah dole,
posouvající síla V = dM/dx. Zatížení působící dolů je kladné.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def prickove_cary(x: np.ndarray, p: np.ndarray, xa: float, xb: float):
    """Příčinkové čáry M a V v řezech x pro jednotkové břemeno v polohách p.

    Vrací matice (len(x), len(p)).
    """
    X = np.asarray(x)[:, None]
    P = np.asarray(p)[None, :]
    L0 = xb - xa
    RB = (P - xa) / L0
    RA = 1.0 - RB
    M = RA * np.where(X > xa, X - xa, 0.0) + RB * np.where(X > xb, X - xb, 0.0) \
        - np.where(P < X, X - P, 0.0)
    V = RA * (X >= xa) + RB * (X > xb) - (P < X)
    return M, V


@dataclass
class ZatezovaciStav:
    """Zatěžovací stav – charakteristické hodnoty.

    rovnomerne: [(q [kN/m], x_od, x_do)]       – spojité zatížení
    bremena: [(F [kN], x)]                      – pevná osamělá břemena
    pohyblive: (síly [kN], rozestupy [m])       – pohyblivá soustava břemen
    tabulka: (x, M, V)                           – vnitřní síly zadané přímo
    """

    nazev: str
    druh: str = "stale"          # stale | promenne
    t: float | None = None       # stáří nosníku při vnesení [dny] (stálá)
    rovnomerne: list[tuple[float, float, float]] = field(default_factory=list)
    bremena: list[tuple[float, float]] = field(default_factory=list)
    pohyblive: tuple[list[float], list[float]] | None = None
    tabulka: tuple[list[float], list[float], list[float]] | None = None
    psi0: float = 0.0
    psi1: float = 0.0
    psi2: float = 0.0
    gamma: float = 1.35          # γ_Q (proměnné) / γ_G,sup (stálé)
    gamma_inf: float = 1.0       # γ_G,inf
    skupina: str = ""
    # vypočtené obálky
    M_max: np.ndarray | None = None
    M_min: np.ndarray | None = None
    V_max: np.ndarray | None = None
    V_min: np.ndarray | None = None

    def spocitej(self, x: np.ndarray, L: float, xa: float, xb: float, n_p: int = 801):
        nx = len(x)
        Mmax = np.zeros(nx)
        Mmin = np.zeros(nx)
        Vmax = np.zeros(nx)
        Vmin = np.zeros(nx)
        promenne = self.druh == "promenne"
        for q, a, b in self.rovnomerne:
            p = np.linspace(a, b, n_p)
            Mi, Vi = prickove_cary(x, p, xa, xb)
            w = np.full(n_p, (b - a) / (n_p - 1))
            w[0] *= 0.5
            w[-1] *= 0.5
            if promenne:  # zatížení jen v nepříznivých částech příčinkové čáry
                Mmax += q * (np.clip(Mi, 0, None) * w).sum(1)
                Mmin += q * (np.clip(Mi, None, 0) * w).sum(1)
                Vmax += q * (np.clip(Vi, 0, None) * w).sum(1)
                Vmin += q * (np.clip(Vi, None, 0) * w).sum(1)
            else:
                m = q * (Mi * w).sum(1)
                v = q * (Vi * w).sum(1)
                Mmax += m
                Mmin += m
                Vmax += v
                Vmin += v
        for F, pos in self.bremena:
            Mi, Vi = prickove_cary(x, np.array([pos]), xa, xb)
            m, v = F * Mi[:, 0], F * Vi[:, 0]
            if promenne:
                Mmax += np.clip(m, 0, None)
                Mmin += np.clip(m, None, 0)
                Vmax += np.clip(v, 0, None)
                Vmin += np.clip(v, None, 0)
            else:
                Mmax += m
                Mmin += m
                Vmax += v
                Vmin += v
        if self.pohyblive:
            sily, rozestupy = self.pohyblive
            off = np.concatenate([[0.0], np.cumsum(rozestupy)])
            starts = np.linspace(-off[-1], L, max(int((L + off[-1]) / 0.02), 200))
            # polohy, kdy některé břemeno stojí přesně nad posuzovaným řezem
            starts = np.union1d(starts, (np.asarray(x)[:, None] - off[None, :]).ravel())
            M_env = np.full((nx, 2), [0.0, 0.0])
            V_env = np.full((nx, 2), [0.0, 0.0])
            Mt = np.zeros((nx, len(starts)))
            Vt = np.zeros((nx, len(starts)))
            for F, o in zip(sily, off):
                pos = starts + o
                Mi, Vi = prickove_cary(x, pos, xa, xb)
                on = (pos >= 0) & (pos <= L)
                Mt += F * Mi * on
                Vt += F * Vi * on
            M_env[:, 0], M_env[:, 1] = Mt.max(1), Mt.min(1)
            V_env[:, 0], V_env[:, 1] = Vt.max(1), Vt.min(1)
            Mmax += np.clip(M_env[:, 0], 0, None)
            Mmin += np.clip(M_env[:, 1], None, 0)
            Vmax += np.clip(V_env[:, 0], 0, None)
            Vmin += np.clip(V_env[:, 1], None, 0)
        if self.tabulka:
            tx, tM, tV = (np.asarray(a, float) for a in self.tabulka)
            m = np.interp(x, tx, tM)
            v = np.interp(x, tx, tV)
            if promenne:
                Mmax += np.clip(m, 0, None)
                Mmin += np.clip(m, None, 0)
                Vmax += np.clip(v, 0, None)
                Vmin += np.clip(v, None, 0)
            else:
                Mmax += m
                Mmin += m
                Vmax += v
                Vmin += v
        self.M_max, self.M_min, self.V_max, self.V_min = Mmax, Mmin, Vmax, Vmin
        return self


@dataclass
class Obalka:
    """Obálka vnitřních sil kombinace."""

    M_max: np.ndarray
    M_min: np.ndarray
    V_max: np.ndarray
    V_min: np.ndarray

    def __add__(self, o: "Obalka") -> "Obalka":
        return Obalka(self.M_max + o.M_max, self.M_min + o.M_min,
                      self.V_max + o.V_max, self.V_min + o.V_min)

    @staticmethod
    def nula(n: int) -> "Obalka":
        z = np.zeros(n)
        return Obalka(z.copy(), z.copy(), z.copy(), z.copy())

    @staticmethod
    def max_z(obalky: list["Obalka"]) -> "Obalka":
        return Obalka(np.max([o.M_max for o in obalky], 0), np.min([o.M_min for o in obalky], 0),
                      np.max([o.V_max for o in obalky], 0), np.min([o.V_min for o in obalky], 0))

    @property
    def V_abs(self) -> np.ndarray:
        return np.maximum(np.abs(self.V_max), np.abs(self.V_min))


def _stala(zs: ZatezovaciStav, g_sup: float, g_inf: float) -> Obalka:
    a = np.stack([g_sup * zs.M_max, g_inf * zs.M_max])
    b = np.stack([g_sup * zs.V_max, g_inf * zs.V_max])
    return Obalka(a.max(0), a.min(0), b.max(0), b.min(0))


def _promenna(zs: ZatezovaciStav, f: float) -> Obalka:
    return Obalka(f * zs.M_max, f * zs.M_min, f * zs.V_max, f * zs.V_min)


def skupiny(promenne: list[ZatezovaciStav]) -> dict[str, list[ZatezovaciStav]]:
    out: dict[str, list[ZatezovaciStav]] = {}
    for z in promenne:
        out.setdefault(z.skupina or z.nazev, []).append(z)
    return out


def kombinace(stale: list[ZatezovaciStav], promenne: list[ZatezovaciStav], druh: str,
              n: int, gamma_G: float = 1.35, gamma_G_inf: float = 1.0,
              xi: float = 0.85, msu_vztah: str = "6.10ab") -> Obalka:
    """Obálka vnějších vnitřních sil pro kombinaci (bez předpětí).

    druh: 'char' | 'casta' | 'kvazistala' | 'msu' | 'stala'
    """
    grp = skupiny(promenne)
    if druh in ("char", "casta", "kvazistala", "stala"):
        G = Obalka.nula(n)
        for z in stale:
            G = G + _stala(z, 1.0, 1.0)
        if druh == "stala" or not grp:
            return G
        if druh == "kvazistala":
            Q = Obalka.nula(n)
            for z in promenne:
                Q = Q + _promenna(z, z.psi2)
            return G + Q
        varianty = []
        for vedouci in grp:
            Q = Obalka.nula(n)
            for g, cleny in grp.items():
                for z in cleny:
                    if druh == "char":
                        f = 1.0 if g == vedouci else z.psi0
                    else:
                        f = z.psi1 if g == vedouci else z.psi2
                    Q = Q + _promenna(z, f)
            varianty.append(G + Q)
        return Obalka.max_z(varianty)
    if druh == "msu":
        def G_(fac: float) -> Obalka:
            o = Obalka.nula(n)
            for z in stale:
                gs = z.gamma if z.gamma else gamma_G
                o = o + _stala(z, fac * gs, z.gamma_inf if z.gamma_inf is not None else gamma_G_inf)
            return o
        varianty = []
        if not grp:
            return G_(1.0)
        if msu_vztah == "6.10ab":
            Q = Obalka.nula(n)
            for z in promenne:
                Q = Q + _promenna(z, z.gamma * z.psi0)
            varianty.append(G_(1.0) + Q)
            Gb = G_(xi)
        else:
            Gb = G_(1.0)
        for vedouci in grp:
            Q = Obalka.nula(n)
            for g, cleny in grp.items():
                for z in cleny:
                    f = z.gamma if g == vedouci else z.gamma * z.psi0
                    Q = Q + _promenna(z, f)
            varianty.append(Gb + Q)
        return Obalka.max_z(varianty)
    raise ValueError(druh)


NAZVY_KOMBINACI = {
    "char": "charakteristická",
    "casta": "častá",
    "kvazistala": "kvazistálá",
    "msu": "MSÚ – základní",
    "stala": "stálá",
}
