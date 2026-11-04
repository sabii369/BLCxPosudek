"""Materiálové modely podle ČSN EN 1992-1-1.

Jednotky: napětí [MPa], moduly [MPa], přetvoření [-], čas [dny].
Znaménková konvence: tah +, tlak − (přetvoření i napětí).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Beton
# ---------------------------------------------------------------------------

#: součinitel s pro vývoj pevnosti v čase podle druhu cementu (3.1.2(6))
CEMENT_S = {"S": 0.38, "N": 0.25, "R": 0.20}
#: součinitele αds1, αds2 pro smršťování vysycháním (příloha B.2)
CEMENT_ALPHA_DS = {"S": (3.0, 0.13), "N": (4.0, 0.12), "R": (6.0, 0.11)}
#: mocnitel α pro úpravu stáří při zatížení podle druhu cementu (B.9)
CEMENT_ALPHA = {"S": -1.0, "N": 0.0, "R": 1.0}


def _parse_tridu(trida: str) -> tuple[float, float]:
    m = re.match(r"\s*C\s*(\d+)\s*/\s*(\d+)", trida.upper())
    if not m:
        raise ValueError(f"Neznámá třída betonu: {trida!r} (očekáváno např. 'C45/55')")
    return float(m.group(1)), float(m.group(2))


@dataclass
class Beton:
    """Beton podle tabulky 3.1 ČSN EN 1992-1-1.

    Všechny charakteristiky se odvozují ze třídy betonu vzorci tabulky 3.1,
    modul pružnosti lze přepsat parametrem ``Ecm``.
    """

    trida: str = "C45/55"
    cement: str = "N"
    gamma_c: float = 1.5
    alpha_cc: float = 1.0
    alpha_ct: float = 1.0
    objemova_tiha: float = 25.0  # kN/m3
    Ecm_zadany: float | None = None
    fck: float = field(init=False)
    fck_cube: float = field(init=False)

    def __post_init__(self):
        self.fck, self.fck_cube = _parse_tridu(self.trida)
        self.cement = self.cement.upper()
        if self.cement not in CEMENT_S:
            raise ValueError("Druh cementu musí být 'S', 'N' nebo 'R'.")

    # --- tabulka 3.1 -------------------------------------------------------
    @property
    def fcm(self) -> float:
        return self.fck + 8.0

    @property
    def fctm(self) -> float:
        if self.fck <= 50:
            return 0.30 * self.fck ** (2.0 / 3.0)
        return 2.12 * math.log(1.0 + self.fcm / 10.0)

    @property
    def fctk005(self) -> float:
        return 0.7 * self.fctm

    @property
    def fctk095(self) -> float:
        return 1.3 * self.fctm

    @property
    def Ecm(self) -> float:
        if self.Ecm_zadany:
            return float(self.Ecm_zadany)
        return 22000.0 * (self.fcm / 10.0) ** 0.3

    @property
    def eps_c2(self) -> float:
        if self.fck <= 50:
            return 2.0e-3
        return (2.0 + 0.085 * (self.fck - 50) ** 0.53) * 1e-3

    @property
    def eps_cu2(self) -> float:
        if self.fck <= 50:
            return 3.5e-3
        return (2.6 + 35.0 * ((90 - self.fck) / 100) ** 4) * 1e-3

    @property
    def n(self) -> float:
        if self.fck <= 50:
            return 2.0
        return 1.4 + 23.4 * ((90 - self.fck) / 100) ** 4

    @property
    def eps_c3(self) -> float:
        if self.fck <= 50:
            return 1.75e-3
        return (1.75 + 0.55 * (self.fck - 50) / 40) * 1e-3

    @property
    def eps_cu3(self) -> float:
        return self.eps_cu2

    @property
    def fcd(self) -> float:
        return self.alpha_cc * self.fck / self.gamma_c

    @property
    def fctd(self) -> float:
        return self.alpha_ct * self.fctk005 / self.gamma_c

    # --- vývoj v čase (3.1.2) ---------------------------------------------
    def beta_cc(self, t: float) -> float:
        """Součinitel β_cc(t) = exp{s·[1 − (28/t)^0,5]}  (3.2)."""
        t = max(float(t), 0.01)
        return math.exp(CEMENT_S[self.cement] * (1.0 - math.sqrt(28.0 / t)))

    def fcm_t(self, t: float) -> float:
        return self.beta_cc(t) * self.fcm

    def fck_t(self, t: float) -> float:
        """f_ck(t) podle 3.1.2(5)."""
        if t >= 28:
            return self.fck
        return max(self.fcm_t(t) - 8.0, 0.0)

    def fctm_t(self, t: float) -> float:
        """f_ctm(t) = β_cc(t)^α · f_ctm  (3.4), α = 1 pro t < 28, 2/3 jinak."""
        a = 1.0 if t < 28 else 2.0 / 3.0
        return self.beta_cc(t) ** a * self.fctm

    def fctk005_t(self, t: float) -> float:
        return 0.7 * self.fctm_t(t)

    def Ecm_t(self, t: float) -> float:
        """E_cm(t) = (f_cm(t)/f_cm)^0,3 · E_cm  (3.5)."""
        return (self.fcm_t(t) / self.fcm) ** 0.3 * self.Ecm

    # --- pracovní diagram pro MSÚ (parabola-obdélník, 3.17) -----------------
    def sigma_msu(self, eps: np.ndarray) -> np.ndarray:
        """Návrhové napětí betonu [MPa] pro přetvoření eps (tlak záporný).

        Tah se zanedbává (napětí 0).
        """
        eps = np.asarray(eps, dtype=float)
        e = np.clip(-eps, 0.0, None)  # tlak kladně
        sig = np.where(
            e < self.eps_c2,
            self.fcd * (1.0 - (1.0 - e / self.eps_c2) ** self.n),
            self.fcd,
        )
        sig = np.where(e > 0, sig, 0.0)
        return -sig


# ---------------------------------------------------------------------------
# Předpínací výztuž
# ---------------------------------------------------------------------------

#: Předvolby předpínací výztuže (EN 10138 / běžné systémy).
PREDPINACI_VYZTUZ = {
    "Y1860S7-15,7": dict(fpk=1860.0, fp01k=1640.0, Ep=195000.0, Ap_lano=150.0, d_lana=15.7,
                         trida_relaxace=2, rho1000=2.5),
    "Y1860S7-15,2": dict(fpk=1860.0, fp01k=1640.0, Ep=195000.0, Ap_lano=140.0, d_lana=15.2,
                         trida_relaxace=2, rho1000=2.5),
    "Y1860S7-12,9": dict(fpk=1860.0, fp01k=1640.0, Ep=195000.0, Ap_lano=100.0, d_lana=12.9,
                         trida_relaxace=2, rho1000=2.5),
    "Y1860S7-12,5": dict(fpk=1860.0, fp01k=1640.0, Ep=195000.0, Ap_lano=93.0, d_lana=12.5,
                         trida_relaxace=2, rho1000=2.5),
    "Y1770S7-15,7": dict(fpk=1770.0, fp01k=1560.0, Ep=195000.0, Ap_lano=150.0, d_lana=15.7,
                         trida_relaxace=2, rho1000=2.5),
    # drát PD 4,5 (podle přiloženého Excelu – σ0,2 = 1200 MPa, f_pk = 1650 MPa)
    "PD4,5": dict(fpk=1650.0, fp01k=1262.25, Ep=195000.0, Ap_lano=15.904, d_lana=4.5,
                  trida_relaxace=1, rho1000=8.0),
}

#: součinitele relaxace podle třídy (3.28)–(3.30): (A, B) pro A·ρ1000·e^{B·μ}
RELAXACE_KOEF = {1: (5.39, 6.7), 2: (0.66, 9.1), 3: (1.98, 8.0)}
RELAXACE_RHO1000 = {1: 8.0, 2: 2.5, 3: 4.0}


@dataclass
class PredpinaciVyztuz:
    """Předpínací výztuž (lano / drát / tyč) podle 3.3 ČSN EN 1992-1-1."""

    typ: str = "Y1860S7-15,7"
    fpk: float | None = None
    fp01k: float | None = None
    Ep: float | None = None
    Ap_lano: float | None = None
    d_lana: float | None = None
    trida_relaxace: int | None = None
    rho1000: float | None = None
    gamma_s: float = 1.15
    eps_uk: float = 0.035
    eps_ud_ku_eps_uk: float = 0.9  # ε_ud = 0,9·ε_uk (3.3.6(7) pozn.)

    def __post_init__(self):
        preset = PREDPINACI_VYZTUZ.get(self.typ, {})
        for k, v in preset.items():
            if getattr(self, k) is None:
                setattr(self, k, v)
        if self.trida_relaxace is None:
            self.trida_relaxace = 2
        if self.rho1000 is None:
            self.rho1000 = RELAXACE_RHO1000[self.trida_relaxace]
        if self.Ep is None:
            self.Ep = 195000.0
        missing = [k for k in ("fpk", "fp01k", "Ap_lano") if getattr(self, k) is None]
        if missing:
            raise ValueError(f"Předpínací výztuž '{self.typ}': chybí {missing}")

    @property
    def fpd(self) -> float:
        return self.fp01k / self.gamma_s

    @property
    def eps_ud(self) -> float:
        return self.eps_ud_ku_eps_uk * self.eps_uk

    @property
    def k(self) -> float:
        return self.fpk / self.fp01k

    def sigma_msu(self, eps: np.ndarray) -> np.ndarray:
        """Návrhový bilineární diagram se stoupající větví (obr. 3.10)."""
        eps = np.asarray(eps, dtype=float)
        e_y = self.fpd / self.Ep
        f_u = self.k * self.fpd  # při ε_uk
        a = np.abs(eps)
        sig = np.where(a <= e_y, self.Ep * a,
                       self.fpd + (f_u - self.fpd) * (a - e_y) / (self.eps_uk - e_y))
        return np.sign(eps) * sig

    def relaxace(self, sigma_pi: float | np.ndarray, t_h: float | np.ndarray) -> np.ndarray:
        """Ztráta relaxací Δσ_pr [MPa] podle (3.28)–(3.30).

        sigma_pi – počáteční napětí [MPa], t_h – čas po napnutí [hod].
        """
        A, B = RELAXACE_KOEF[int(self.trida_relaxace)]
        s = np.asarray(sigma_pi, dtype=float)
        mu = s / self.fpk
        t = np.maximum(np.asarray(t_h, dtype=float), 0.0)
        val = A * self.rho1000 * np.exp(B * mu) * (t / 1000.0) ** (0.75 * (1.0 - mu)) * 1e-5
        return s * val

    def cas_relaxace(self, sigma_pi: float | np.ndarray, rho: float | np.ndarray) -> np.ndarray:
        """Inverze (3.28)–(3.30): doba [h], za kterou při napětí sigma_pi dosáhne relativní ztráta
        relaxací Δσ_pr/σ_pi hodnoty rho (ekvivalentní čas)."""
        A, B = RELAXACE_KOEF[int(self.trida_relaxace)]
        s = np.asarray(sigma_pi, dtype=float)
        mu = np.clip(s / self.fpk, 1e-6, 0.999)
        r = np.maximum(np.asarray(rho, dtype=float), 0.0)
        zaklad = r / (A * self.rho1000 * np.exp(B * mu) * 1e-5)
        return 1000.0 * zaklad ** (1.0 / (0.75 * (1.0 - mu)))

    @property
    def popis_relaxace(self) -> str:
        A, B = RELAXACE_KOEF[int(self.trida_relaxace)]
        return f"{A}·ρ1000·e^({B}·μ)·(t/1000)^(0,75·(1−μ))·10⁻⁵"


# ---------------------------------------------------------------------------
# Betonářská výztuž
# ---------------------------------------------------------------------------

BETONARSKA_VYZTUZ = {
    "B500B": dict(fyk=500.0, Es=200000.0, k=1.08, eps_uk=0.05),
    "B500A": dict(fyk=500.0, Es=200000.0, k=1.05, eps_uk=0.025),
    "B500C": dict(fyk=500.0, Es=200000.0, k=1.15, eps_uk=0.075),
}


@dataclass
class BetonarskaVyztuz:
    typ: str = "B500B"
    fyk: float | None = None
    Es: float | None = None
    k: float | None = None
    eps_uk: float | None = None
    gamma_s: float = 1.15
    eps_ud_ku_eps_uk: float = 0.9

    def __post_init__(self):
        preset = BETONARSKA_VYZTUZ.get(self.typ, BETONARSKA_VYZTUZ["B500B"])
        for k, v in preset.items():
            if getattr(self, k) is None:
                setattr(self, k, v)

    @property
    def fyd(self) -> float:
        return self.fyk / self.gamma_s

    @property
    def eps_ud(self) -> float:
        return self.eps_ud_ku_eps_uk * self.eps_uk

    def sigma_msu(self, eps: np.ndarray) -> np.ndarray:
        eps = np.asarray(eps, dtype=float)
        e_y = self.fyd / self.Es
        a = np.abs(eps)
        sig = np.where(a <= e_y, self.Es * a,
                       self.fyd + (self.k - 1.0) * self.fyd * (a - e_y) / (self.eps_uk - e_y))
        return np.sign(eps) * sig
