"""Nerovnoměrná (nelineární) složka teploty – primární (vlastní) napětí v průřezu.

ČSN EN 1991-1-5, čl. 6.1.4.2 (postup 2) a příloha B, tab. B.3 – betonová mostovka (typ 3):
rozdělení teploty po výšce průřezu pro oteplení (horní povrch teplejší) a ochlazení, závislé na
výšce průřezu h a na tloušťce mostního svršku. Nelineární část rozdělení vyvolá ve staticky určitém
nosníku jen primární napětí (rovnovážná v průřezu: N = 0, M = 0):

    σ(z) = E·α·(ε̄ + κ̄·(z − z_t) − ΔT(z)),   ε̄ = ∫ΔT·b dz / A,   κ̄ = ∫ΔT·(z − z_t)·b dz / I

(tah +, tlak −; z od spodního okraje). Primární napětí se v kombinacích násobí součiniteli γ·ψ
a přičítají k napětí v betonu jen tehdy, když jsou nepříznivá.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ČSN EN 1991-1-5, tab. B.3 – h [m] → oteplení (ΔT1, ΔT2, ΔT3) a ochlazení (ΔT1, ΔT2, ΔT3, ΔT4) [°C]
_H = (0.2, 0.4, 0.6, 0.8, 1.0, 1.5)
_OCHLAZENI_BEZ = ((-4.7, -1.7, 0.0, -0.7), (-9.0, -3.5, -0.4, -2.9), (-11.8, -4.0, -0.9, -4.6),
                  (-12.8, -3.3, -0.9, -5.6), (-13.4, -3.0, -0.9, -6.4), (-13.7, -1.0, -0.6, -6.7))
TAB_B3 = {
    "bez": ((((12.0, 5.0, 0.1), (15.2, 4.4, 1.2), (15.2, 4.0, 1.4), (15.4, 4.0, 2.0), (15.4, 4.0, 2.0),
              (15.4, 4.5, 2.0))), _OCHLAZENI_BEZ),
    "izolace": ((((19.5, 8.5, 0.0), (23.6, 6.5, 1.0), (23.6, 6.0, 1.4), (23.6, 5.0, 1.4), (23.6, 5.0, 1.4),
                  (23.6, 5.0, 1.4))), _OCHLAZENI_BEZ),
}
# svršek tloušťky 50, 100, 150, 200 mm: h → [hodnoty pro jednotlivé tloušťky]
_HS = (0.05, 0.10, 0.15, 0.20)
_OTEPLENI_SVRSEK = (
    ((13.2, 4.9, 0.3), (8.5, 3.5, 0.5), (5.6, 2.5, 0.2), (3.7, 2.0, 0.5)),
    ((17.2, 4.6, 1.4), (12.0, 3.0, 1.5), (8.5, 2.0, 1.2), (6.2, 1.3, 1.0)),
    ((17.6, 4.0, 1.8), (13.0, 3.0, 2.0), (9.7, 2.2, 1.7), (7.2, 1.5, 1.5)),
    ((17.8, 4.0, 2.1), (13.5, 3.0, 2.5), (10.0, 2.5, 2.0), (7.5, 2.1, 1.5)),
    ((17.8, 4.0, 2.1), (13.5, 3.0, 2.5), (10.0, 2.5, 2.0), (7.5, 2.1, 1.5)),
    ((17.8, 4.0, 2.1), (13.5, 3.0, 2.5), (10.0, 2.5, 2.0), (7.5, 2.1, 1.5)),
)
_OCHLAZENI_SVRSEK = (
    ((-3.1, -1.0, -0.2, -1.2), (-2.0, -0.5, -0.5, -1.5), (-1.1, -0.3, -0.7, -1.7), (-0.5, -0.2, -1.0, -1.8)),
    ((-6.4, -2.3, -0.6, -3.2), (-4.5, -1.4, -1.0, -3.5), (-3.2, -0.9, -1.4, -3.8), (-2.2, -0.5, -1.9, -4.0)),
    ((-8.7, -2.7, -1.2, -4.9), (-6.5, -1.8, -1.5, -5.0), (-4.9, -1.1, -1.7, -5.1), (-3.6, -0.6, -1.9, -5.1)),
    ((-9.8, -2.4, -1.2, -5.8), (-7.6, -1.7, -1.5, -6.0), (-5.8, -1.3, -1.7, -6.2), (-4.5, -1.0, -1.9, -6.0)),
    ((-10.3, -2.1, -1.2, -6.3), (-8.0, -1.5, -1.5, -6.3), (-6.2, -1.1, -1.7, -6.2), (-4.3, -0.9, -1.9, -5.8)),
    ((-10.6, -0.7, -0.8, -6.6), (-8.4, -0.5, -1.0, -6.5), (-6.5, -0.4, -1.1, -6.2), (-5.0, -0.3, -1.2, -5.6)),
)

# výchozí dílčí součinitele (γ, ψ) teploty v kombinacích (ČSN EN 1990, příl. A2: ψ0 = ψ1 = 0,6, ψ2 = 0,5)
SOUCINITELE_VYCHOZI = {"char": (1.0, 0.6), "casta": (1.0, 0.6), "kvazistala": (1.0, 0.5),
                       "6.10a": (1.5, 0.6), "6.10b": (1.5, 0.6), "6.10": (1.5, 0.6)}
VARIANTY = ("oteplení", "ochlazení")


def _interp(x: float, xs, ys) -> np.ndarray:
    """Lineární interpolace řádků tabulky (mimo rozsah krajní hodnota)."""
    ys = np.asarray(ys, dtype=float)
    return np.array([np.interp(x, xs, ys[:, j]) for j in range(ys.shape[1])])


def rozdily_teplot(h: float, svrsek) -> tuple[np.ndarray, np.ndarray]:
    """(ΔT oteplení [3], ΔT ochlazení [4]) [°C] podle tab. B.3 pro výšku h [m] a svršek
    ("bez" | "izolace" | tloušťka [m]) – lineární interpolace mezi řádky tabulky."""
    sv = svrsek_klic(svrsek)
    if isinstance(sv, str):
        ot, och = TAB_B3[sv]
        return _interp(h, _H, ot), _interp(h, _H, och)
    ot = np.array([_interp(sv, _HS, r) for r in _OTEPLENI_SVRSEK])
    och = np.array([_interp(sv, _HS, r) for r in _OCHLAZENI_SVRSEK])
    return _interp(h, _H, ot), _interp(h, _H, och)


def svrsek_klic(svrsek):
    """"bez" | "izolace" | tloušťka svršku [m] (> 0)."""
    if svrsek in (None, "", 0, 0.0):
        return "bez"
    if isinstance(svrsek, str):
        s = svrsek.strip().lower()
        if s.startswith("bez"):
            return "bez"
        if s.startswith(("izol", "vodot")):
            return "izolace"
        try:
            svrsek = float(s.replace(",", "."))
        except ValueError:
            raise ValueError(f"Teplota: svršek „{svrsek}“ – zadejte bez, izolace nebo tloušťku [m].")
        if svrsek == 0:
            return "bez"
    svrsek = float(svrsek)
    if svrsek < 0:
        raise ValueError("Teplota: tloušťka svršku nesmí být záporná.")
    return svrsek


def profil(h: float, dT_ot, dT_och, h_svrsek: float = 0.0) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Body rozdělení teploty {varianta: (z [m] od spodu, ΔT [°C])} podle obr. 6.2c."""
    t1 = min(0.3 * h, 0.15)
    t2 = min(max(0.3 * h, 0.10), 0.25)
    t3 = min(0.3 * h, 0.10 + h_svrsek, h - t1 - t2)
    ot = (np.array([0.0, t3, h - t1 - t2, h - t1, h]),
          np.array([dT_ot[2], 0.0, 0.0, dT_ot[1], dT_ot[0]]))
    c1 = min(0.2 * h, 0.25)     # h1 = h4
    c2 = min(0.25 * h, 0.20)    # h2 = h3
    och = (np.array([0.0, c1, c1 + c2, h - c1 - c2, h - c1, h]),
           np.array([dT_och[3], dT_och[2], 0.0, 0.0, dT_och[1], dT_och[0]]))
    return {"oteplení": ot, "ochlazení": och}


@dataclass
class Teplota:
    """Zadání nerovnoměrné složky teploty ([teplota] ve vstupu)."""

    svrsek: object = "bez"            # "bez" | "izolace" | tloušťka svršku [m]
    alfa: float = 1e-5                # součinitel teplotní roztažnosti [1/K]
    E: float | None = None            # MPa (None = E_cm betonu)
    otepleni: list | None = None      # [ΔT1, ΔT2, ΔT3] °C (None = tab. B.3)
    ochlazeni: list | None = None     # [ΔT1, ΔT2, ΔT3, ΔT4] °C, záporné (None = tab. B.3)
    soucinitele: dict = field(default_factory=lambda: dict(SOUCINITELE_VYCHOZI))

    @classmethod
    def ze_slovniku(cls, d: dict | None) -> "Teplota | None":
        if not d or not d.get("uvazovat", True):
            return None
        souc = dict(SOUCINITELE_VYCHOZI)
        for k, v in (d.get("soucinitele") or {}).items():
            if k not in souc:
                raise ValueError(f"Teplota: neznámá kombinace „{k}“ (možnosti: {', '.join(souc)}).")
            if len(v) != 2:
                raise ValueError(f"Teplota: kombinace {k} – zadejte [γ, ψ].")
            souc[k] = (float(v[0]), float(v[1]))
        ot = d.get("otepleni", d.get("oteplení"))
        och = d.get("ochlazeni")
        if ot is not None and len(ot) != 3:
            raise ValueError("Teplota: oteplení – zadejte [ΔT1, ΔT2, ΔT3].")
        if och is not None and len(och) != 4:
            raise ValueError("Teplota: ochlazení – zadejte [ΔT1, ΔT2, ΔT3, ΔT4].")
        t = cls(svrsek=d.get("svrsek", "bez"), alfa=float(d.get("alfa", 1e-5)),
                E=float(d["E"]) if d.get("E") not in (None, "") else None,
                otepleni=[float(v) for v in ot] if ot is not None else None,
                ochlazeni=[float(v) for v in och] if och is not None else None, soucinitele=souc)
        svrsek_klic(t.svrsek)
        return t

    def faktor(self, druh: str) -> float:
        g, p = self.soucinitele.get(druh, (0.0, 0.0))
        return g * p

    def spocitej(self, prurez, Ecm: float) -> "VysledekTeploty":
        """Primární napětí v průřezu (prurez v mm, z od spodního okraje)."""
        h = prurez.h * 1e-3
        sv = svrsek_klic(self.svrsek)
        dT_ot, dT_och = rozdily_teplot(h, sv)
        zadane = []
        if self.otepleni is not None:
            dT_ot, _ = np.array(self.otepleni, float), zadane.append("oteplení")
        if self.ochlazeni is not None:
            dT_och, _ = -np.abs(np.array(self.ochlazeni, float)), zadane.append("ochlazení")
        h_sv = sv if not isinstance(sv, str) else 0.0
        prof = profil(h, dT_ot, dT_och, h_sv)
        E = self.E or Ecm
        # integrace po tenkých pásech (stejná síť pro A, z_t, I → rovnováha N = 0, M = 0 přesně)
        n = 4000
        dz = prurez.h / n
        zp = (np.arange(n) + 0.5) * dz
        bp = prurez.sirka(zp)
        A = float(np.sum(bp) * dz)
        zt = float(np.sum(bp * zp) * dz / A)
        I = float(np.sum(bp * (zp - zt) ** 2) * dz)
        var = {}
        for k, (zb, dT) in prof.items():
            T = np.interp(zp, zb * 1e3, dT)
            e0 = float(np.sum(T * bp) * dz / A)
            k0 = float(np.sum(T * (zp - zt) * bp) * dz / I)    # 1/mm (× α)
            N = E * self.alfa * float(np.sum(T * bp) * dz) * 1e-3        # kN
            M = E * self.alfa * float(np.sum(T * (zp - zt) * bp) * dz) * 1e-6   # kNm
            var[k] = dict(z=zb * 1e3, dT=dT, e0=e0, k0=k0, N=N, M=M)
        return VysledekTeploty(self, h, sv, dT_ot, dT_och, zadane, E, A, zt, I, var)


@dataclass
class VysledekTeploty:
    zadani: Teplota
    h: float                 # m
    svrsek: object
    dT_ot: np.ndarray
    dT_och: np.ndarray
    zadane: list
    E: float                 # MPa
    A: float                 # mm²
    zt: float                # mm
    I: float                 # mm⁴
    var: dict                # varianta → z [mm], ΔT, ε̄/α, κ̄/α, N, M

    def dT(self, z, varianta: str) -> np.ndarray:
        v = self.var[varianta]
        return np.interp(z, v["z"], v["dT"])

    def sigma(self, z, varianta: str) -> np.ndarray:
        """Charakteristické primární napětí [MPa] ve výšce z [mm] (tah +)."""
        v = self.var[varianta]
        z = np.asarray(z, dtype=float)
        return self.E * self.zadani.alfa * (v["e0"] + v["k0"] * (z - self.zt) - self.dT(z, varianta))

    def navrhove(self, z, druh: str, varianta: str | None) -> np.ndarray | float:
        """γ·ψ·σ_T(z) pro kombinaci druh (varianta None = teplota nepůsobí)."""
        if varianta is None:
            return 0.0
        return self.zadani.faktor(druh) * self.sigma(z, varianta)

    def popis_svrsku(self) -> str:
        if self.svrsek == "bez":
            return "bez svršku"
        if self.svrsek == "izolace":
            return "vodotěsná izolace"
        return f"svršek tloušťky {self.svrsek * 1e3:.0f} mm"
