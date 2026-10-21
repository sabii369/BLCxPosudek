"""
prefabrikaty.py
===============
Typické prefabrikované nosníky – předvyplnění vstupů v GUI.

Tabulka se načte ze souboru „data/Prefabrikáty.xlsx“ v balíčku, pokud existuje
a je k dispozici openpyxl.
Jinak se použije vestavěná kopie tabulky níže.

Sloupce: Prefabrikát | Rozpětí (typické) | šířka b | Iy | Spára (ANO/NE) |
         šířka spáry | Iy spáry
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Prefabrikat:
    nazev: str
    L: float              # typické rozpětí [m]
    b: float              # šířka nosníku [m]
    Iy: float             # moment setrvačnosti nosníku [m⁴]
    spara: bool
    b_s: float = 0.0      # šířka spáry [m]
    Iy_s: float = 0.0     # moment setrvačnosti spáry [m⁴]


_VESTAVENE = [
    ("I-62 / 24", 23, 1.15, 0.074085746421938, True, 0.35, 0.0163632),
    ("I-62 / 27", 26, 1.15, 0.094521142989135, True, 0.35, 0.0202692),
    ("I-62 / 30", 29, 1.15, 0.130581081191634, True, 0.35, 0.0269157),
    ("I-67 / 21", 20, 1.15, 0.074085746421938, True, 0.35, 0.0163632),
    ("I-67 / 24", 23, 1.15, 0.094521142989135, True, 0.35, 0.0202692),
    ("I-67 / 27", 26, 1.15, 0.130581081191634, True, 0.35, 0.0269157),
    ("I-67 / 30", 29, 1.15, 0.173415441489877, True, 0.35, 0.0345072),
    ("I-73 / 21", 20, 1.15, 0.074085746421938, True, 0.35, 0.0163632),
    ("I-73 / 24", 23, 1.15, 0.094521142989135, True, 0.35, 0.0202692),
    ("I-73 / 27", 26, 1.15, 0.130581081191634, True, 0.35, 0.0269157),
    ("I-73 / 30", 29, 1.15, 0.173415441489877, True, 0.35, 0.0345072),
    ("KA-61 / 9", 9, 1.0, 0.006663, False, 0.0, 0.0),
    ("KA-61 / 12", 12, 1.0, 0.014375, False, 0.0, 0.0),
    ("KA-61 / 15", 15, 1.0, 0.021443, False, 0.0, 0.0),
    ("KA-61 / 18", 18, 1.0, 0.035184, False, 0.0, 0.0),
    ("KA-61 / 21", 21, 1.0, 0.067293, False, 0.0, 0.0),
    ("KA-67 / 9", 9, 1.0, 0.006663, False, 0.0, 0.0),
    ("KA-67 / 12", 12, 1.0, 0.014375, False, 0.0, 0.0),
    ("KA-67 / 15", 15, 1.0, 0.021443, False, 0.0, 0.0),
    ("KA-67 / 18", 18, 1.0, 0.035184, False, 0.0, 0.0),
    ("KA-73 / 9", 9, 1.0, 0.006663, False, 0.0, 0.0),
    ("KA-73 / 12", 12, 1.0, 0.014375, False, 0.0, 0.0),
    ("KA-73 / 15", 15, 1.0, 0.021443, False, 0.0, 0.0),
    ("KA-73 / 18", 18, 1.0, 0.035184, False, 0.0, 0.0),
]

NAZEV_SOUBORU = "Prefabrikáty.xlsx"


def _cislo(v) -> float:
    if v is None or v == "":
        return 0.0
    return float(str(v).replace(",", "."))


def _nacti_xlsx(cesta: str) -> List[Prefabrikat]:
    import openpyxl
    wb = openpyxl.load_workbook(cesta, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    out = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or row is None or row[0] is None or str(row[0]).strip() == "":
            continue
        spara = str(row[4]).strip().upper() in ("ANO", "A", "YES", "1", "TRUE")
        out.append(Prefabrikat(str(row[0]).strip(), _cislo(row[1]), _cislo(row[2]),
                               _cislo(row[3]), spara,
                               _cislo(row[5]) if spara else 0.0,
                               _cislo(row[6]) if spara else 0.0))
    return out


def nacti_prefabrikaty() -> tuple[Dict[str, Prefabrikat], str]:
    """Vrátí (slovník název → Prefabrikat, popis zdroje)."""
    cesta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", NAZEV_SOUBORU)
    if os.path.isfile(cesta):
        try:
            seznam = _nacti_xlsx(cesta)
            if seznam:
                return {p.nazev: p for p in seznam}, cesta
        except Exception:
            pass
    return {t[0]: Prefabrikat(*t) for t in _VESTAVENE}, "vestavěná tabulka"


def prefabrikat(nazev: str) -> Optional[Prefabrikat]:
    return nacti_prefabrikaty()[0].get(nazev.strip())
