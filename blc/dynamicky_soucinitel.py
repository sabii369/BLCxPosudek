"""
dynamicky_soucinitel.py
=======================
Dynamický součinitel δ pohyblivého zatížení podle ČSN 73 6222 (Zatížitelnost mostů
pozemních komunikací), kapitola 8.

δ násobí statické účinky zatížení dopravou (čl. 8.1.1) a závisí na druhu zatížitelnosti
(čl. 8.1.3):
  normální zatížitelnost Vn (čl. 8.2.1 b–d): zatížení jedním / dvěma / třemi a více
      zatěžovacími pruhy (a pruhy Δi)  δ = δ1 / δ2 / δ3,
  výhradní zatížitelnost Vr (čl. 8.3.1 b): zatížení celým vozidlem  δ = δ1,
  výjimečná zatížitelnost Ve (čl. 8.4): zatížení jedním kolem / nápravou (a) i více nápravami,
      celou soupravou (b)  δ = 1,05 – nezávisí na rozpětí ani na vlastní frekvenci,
  rovnoměrné zatížení chodníků (čl. 8.5 b)  δ = 1,00.
Součinitele δ1, δ2, δ3 podle vlastní frekvence f = 90,6·L_d^−0,923 (čl. 8.7.1, obr. 8.1,
lineárně mezi zlomy 1,0 – 2,5 – 4,5 – 6,0 Hz), náhradní délka L_d podle tab. 8.1: konstrukce
o jednom poli – kolmá vzdálenost uložení (u šikmé L·sin α), spojitá – průměr rozpětí polí.
Místní účinky jednoho kola / nápravy (čl. 8.2.1 a, 8.2.2: δ = 1,40 / 2,0) se u nosníků
neuvažují.  Pro vozidla MLC norma dynamický součinitel neuvádí – uvažuje se δ = 1,0,
pokud není zadán.
"""

from __future__ import annotations
from .cisla import cz
import math
from typing import Dict, Optional, Tuple

import numpy as np

NORMA = "ČSN 73 6222"
DELTA_VE = 1.05            # čl. 8.4 a), b)
DELTA_CHODNIKY = 1.00      # čl. 8.5 b)

# obr. 8.1 – zlomy f [Hz] a hodnoty δ1, δ2, δ3 (mimo rozsah konstantní)
_F_ZLOMY = (1.0, 2.5, 4.5, 6.0)
_DELTY = {1: (1.20, 1.40, 1.40, 1.25), 2: (1.17, 1.30, 1.30, 1.20), 3: (1.13, 1.20, 1.20, 1.15)}


def nahradni_delka(K) -> Tuple[float, str]:
    """Náhradní délka L_d [m] (tab. 8.1) a odkaz: jedno pole – kolmá vzdálenost uložení
    (ř. 2, 3; šikmý most L·sin α), spojitá konstrukce – aritmetický průměr rozpětí (ř. 8)."""
    sin_a = 1.0 / math.sqrt(1.0 + K.cot ** 2)
    L = sum(K.L) / len(K.L)
    return L * sin_a, ("tab. 8.1, ř. 3" if K.n_poli == 1 else "tab. 8.1, ř. 8")


def vlastni_frekvence(Ld: float) -> float:
    """Vlastní frekvence nosné konstrukce f [Hz] z náhradní délky (čl. 8.7.1, vzorec (1))."""
    if Ld <= 0:
        raise ValueError("Náhradní délka L_d musí být kladná.")
    return 90.6 * Ld ** -0.923


def delta_i(i: int, f: float) -> float:
    """δ1, δ2, δ3 (i = 1, 2, 3; i > 3 → δ3) pro vlastní frekvenci f [Hz] (obr. 8.1)."""
    return float(np.interp(f, _F_ZLOMY, _DELTY[min(max(int(i), 1), 3)]))


def delty_zatizitelnosti(K, dyn: Optional[float] = None) -> Tuple[Dict[int, float], str]:
    """{1: δ1, 2: δ2, 3: δ3} pro konstrukci K a zdůvodnění; dyn (zadané) = všechny δ_i = dyn."""
    if dyn is not None:
        if dyn <= 0:
            raise ValueError("Dynamický součinitel musí být kladný.")
        return {i: float(dyn) for i in (1, 2, 3)}, "zadáno"
    Ld, tab = nahradni_delka(K)
    f = vlastni_frekvence(Ld)
    d = {i: delta_i(i, f) for i in (1, 2, 3)}
    return d, (f"{NORMA}, čl. 8.6, obr. 8.1: L_d = {cz(Ld, 2)} m ({tab}), f = 90,6·L_d^−0,923 = "
               f"{cz(f, 2)} Hz → δ1 = {cz(d[1], 3, g=True)}, δ2 = {cz(d[2], 3, g=True)}, δ3 = {cz(d[3], 3, g=True)}")


def dynamicky_soucinitel(vozidlo: str, dyn: Optional[float] = None, K=None) -> Tuple[float, str]:
    """
    Dynamický součinitel δ pro vozidlo a zdůvodnění do protokolu.

    Args:
        vozidlo: "Ve" (výjimečná zatížitelnost) | "Vr" (výhradní – celé vozidlo, δ1; potřebuje
                 konstrukci K) | "MLC" (vojenské vozidlo).
        dyn:     zadaná hodnota δ (má přednost); None = podle ČSN 73 6222, kap. 8.
        K:       konstrukce (Konstrukce) – pro δ1 výhradní zatížitelnosti.

    Returns:
        (δ [-], zdroj) – zdroj např. „ČSN 73 6222, čl. 8.4, výjimečná zatížitelnost“, „zadáno“.
    """
    if dyn is not None:
        if dyn <= 0:
            raise ValueError("Dynamický součinitel musí být kladný.")
        return float(dyn), "zadáno"
    if vozidlo == "Ve":
        return DELTA_VE, f"{NORMA}, čl. 8.4, výjimečná zatížitelnost"
    if vozidlo == "Vr":
        if K is None:
            raise ValueError("Pro δ výhradní zatížitelnosti je nutná konstrukce K.")
        Ld, tab = nahradni_delka(K)
        f = vlastni_frekvence(Ld)
        return delta_i(1, f), (f"{NORMA}, čl. 8.3.1 b), obr. 8.1: δ = δ1, L_d = {cz(Ld, 2)} m ({tab}), "
                               f"f = {cz(f, 2)} Hz")
    if vozidlo == "MLC":
        return 1.0, f"pro MLC {NORMA} dynamický součinitel neuvádí"
    raise ValueError(f"Neznámé vozidlo '{vozidlo}' (Ve, Vr, MLC).")
