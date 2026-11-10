"""
dynamicky_soucinitel.py
=======================
Dynamický součinitel δ pohyblivého zatížení podle ČSN 73 6222 (Zatížitelnost mostů
pozemních komunikací), kapitola 8.

δ násobí statické účinky zatížení dopravou (čl. 8.1.1) a závisí na druhu zatížitelnosti
(čl. 8.1.3):
  výjimečná zatížitelnost Ve (čl. 8.4): zatížení jedním kolem / nápravou (a) i více nápravami,
      celou soupravou (b)  δ = 1,05 – nezávisí na rozpětí ani na vlastní frekvenci,
  rovnoměrné zatížení chodníků (čl. 8.5 b)  δ = 1,00.
Součinitele δ1, δ2, δ3 podle vlastní frekvence (obr. 8.1, čl. 8.6, 8.7) platí pro normální
a výhradní zatížitelnost (Vn, Vr), které program zatím nepočítá.  Pro vozidla MLC norma
dynamický součinitel neuvádí – uvažuje se δ = 1,0, pokud není zadán.
"""

from __future__ import annotations
from typing import Optional, Tuple

NORMA = "ČSN 73 6222"
DELTA_VE = 1.05            # čl. 8.4 a), b)
DELTA_CHODNIKY = 1.00      # čl. 8.5 b)


def dynamicky_soucinitel(vozidlo: str, dyn: Optional[float] = None) -> Tuple[float, str]:
    """
    Dynamický součinitel δ pro vozidlo a zdůvodnění do protokolu.

    Args:
        vozidlo: "Ve" (výjimečná zatížitelnost) | "MLC" (vojenské vozidlo).
        dyn:     zadaná hodnota δ (má přednost); None = podle ČSN 73 6222, kap. 8.

    Returns:
        (δ [-], zdroj) – zdroj např. „ČSN 73 6222, čl. 8.4, výjimečná zatížitelnost“, „zadáno“.
    """
    if dyn is not None:
        if dyn <= 0:
            raise ValueError("Dynamický součinitel musí být kladný.")
        return float(dyn), "zadáno"
    if vozidlo == "Ve":
        return DELTA_VE, f"{NORMA}, čl. 8.4, výjimečná zatížitelnost"
    if vozidlo == "MLC":
        return 1.0, f"pro MLC {NORMA} dynamický součinitel neuvádí"
    raise ValueError(f"Neznámé vozidlo '{vozidlo}' (Ve, MLC).")
